"""Local persistence, DPAPI isolation and credential destination boundaries."""
from io import BytesIO
import json
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from pattern_reborn.config import load_provider_config
from pattern_reborn.generation.base import ProviderId
from pattern_reborn.web_api import create_app
from tests.test_web_creative import ROOT, SECRET, creative, payload, setup_key, submit, wait_job  # noqa: F401


HEADERS = {'X-Pattern-Reborn': 'local-workspace'}


def selected(result, identifier='seedream'):
    return next(p for p in result['providers'] if p['id'] == identifier)


def test_restart_new_cookie_recovers_encrypted_key_and_all_settings(creative, monkeypatch):
    import pattern_reborn.web_creative as routes
    monkeypatch.setattr(routes, 'build_generation_service', creative['adapter'].factory)
    monkeypatch.setenv('PATTERN_REBORN_OUTPUTS', str(creative['output']))
    change = {'provider': 'custom', 'default_provider': 'custom', 'base_url': 'https://thirdparty.example/v2/images/edits',
              'model': 'vendor/custom-model', 'protocol': 'openai_images_edits', 'size_options': ['768x768', '2K'], 'api_key': SECRET}
    result = creative['client'].put('/api/settings', json=change)
    assert result.status_code == 200, result.text
    disk = creative['settings_path'].read_text(encoding='utf-8')
    assert SECRET not in disk and 'windows-dpapi-current-user' in disk
    for unused in range(2):
        with TestClient(create_app(creative['repository'].workspace, settings_path=creative['settings_path']), headers=HEADERS) as client:
            state = {**creative, 'client': client}
            settings = client.get('/api/settings').json()
            assert settings['default_provider'] == 'custom' and not settings['session_only']
            provider = selected(settings, 'custom')
            assert provider['base_url'] == change['base_url'] and provider['model'] == change['model']
            assert provider['protocol'] == change['protocol'] and provider['size_options'] == change['size_options']
            assert provider['stored_credential'] and SECRET not in json.dumps(settings)
            if unused == 0:
                continue
            response, _ = submit(state, provider='custom', size='768x768')
            assert response.status_code == 202, response.text
            assert wait_job(state, response.json()['job'])['job']['status'] == 'succeeded'
            assert creative['adapter'].calls[0][1] == SECRET


def test_omitted_password_preserves_and_explicit_empty_clears_on_disk(creative):
    before = setup_key(creative)
    token = selected(before)['settings_revision']
    response = creative['client'].put('/api/settings', json={'provider': 'seedream', 'model': 'model-2'})
    assert response.status_code == 200 and selected(response.json())['stored_credential']
    assert selected(response.json())['settings_revision'] != token
    response = creative['client'].put('/api/settings', json={'provider': 'seedream', 'api_key': None})
    assert response.status_code == 200 and selected(response.json())['stored_credential']
    # Reading through an entirely new application decrypts the retained key.
    with TestClient(create_app(creative['repository'].workspace, settings_path=creative['settings_path']), headers=HEADERS) as client:
        assert selected(client.get('/api/settings').json())['stored_credential']
        response = client.put('/api/settings', json={'provider': 'seedream', 'api_key': ''})
        assert response.status_code == 200 and not selected(response.json())['stored_credential']
    disk = json.loads(creative['settings_path'].read_text(encoding='utf-8'))
    assert disk['providers']['seedream']['encrypted_key'] is None
    assert disk['providers']['seedream']['key_endpoint'] is None


def test_failed_atomic_replace_preserves_disk_and_live_state(creative, monkeypatch):
    import pattern_reborn.provider_store as store
    setup_key(creative)
    old = creative['settings_path'].read_bytes()
    previous = creative['client'].get('/api/settings').json()
    with monkeypatch.context() as patch:
        def fail_replace(*args):
            raise OSError('sensitive disk error content')
        patch.setattr(store.os, 'replace', fail_replace)
        response = creative['client'].put('/api/settings', json={'provider': 'seedream', 'model': 'will-not-save', 'api_key': 'new-secret'})
    assert response.status_code == 503
    assert 'sensitive disk' not in response.text and 'new-secret' not in response.text
    assert creative['settings_path'].read_bytes() == old
    assert creative['client'].get('/api/settings').json() == previous
    assert not list(creative['settings_path'].parent.glob('*.tmp'))


def test_corrupt_settings_retained_and_never_overwritten(creative):
    path = creative['settings_path']
    path.parent.mkdir(exist_ok=True)
    corrupt = b'{broken-sensitive-private-content'
    path.write_bytes(corrupt)
    with TestClient(create_app(creative['repository'].workspace, settings_path=path), headers=HEADERS) as client:
        settings = client.get('/api/settings')
        assert settings.status_code == 200 and settings.json()['config_error']
        assert '.private/provider-settings.json' in settings.json()['config_error']
        assert 'sensitive-private' not in settings.text
        response = client.put('/api/settings', json={'provider': 'seedream', 'api_key': SECRET})
        assert response.status_code == 503 and SECRET not in response.text
    assert path.read_bytes() == corrupt


def test_undecryptable_settings_retained_without_plaintext_fallback(creative):
    setup_key(creative)
    path = creative['settings_path']
    data = json.loads(path.read_text(encoding='utf-8'))
    data['providers']['seedream']['encrypted_key'] = 'aW52YWxpZC1kcGFwaS1ibG9i'
    path.write_text(json.dumps(data), encoding='utf-8')
    before = path.read_bytes()
    with TestClient(create_app(creative['repository'].workspace, settings_path=path), headers=HEADERS) as client:
        settings = client.get('/api/settings').json()
        assert settings['config_error'] and not settings['providers']
        assert client.put('/api/settings', json={'provider': 'seedream', 'api_key': SECRET}).status_code == 503
    assert path.read_bytes() == before and SECRET.encode() not in before


def test_encryption_failure_never_saves_plaintext_or_live_key(creative, monkeypatch):
    import pattern_reborn.provider_store as store
    def unavailable(*args, **kwargs):
        raise store.SettingsStoreError('Windows 加密暂不可用。')
    monkeypatch.setattr(store, '_dpapi', unavailable)
    response = creative['client'].put('/api/settings', json={'provider': 'seedream', 'api_key': SECRET})
    assert response.status_code == 503 and SECRET not in response.text
    assert not creative['settings_path'].exists()
    assert not selected(creative['client'].get('/api/settings').json())['stored_credential']


def test_destination_change_requires_fresh_key_and_blocks_environment_fallback(creative, monkeypatch):
    setup_key(creative)
    previous = creative['settings_path'].read_bytes()
    change = {'provider': 'seedream', 'base_url': 'https://new-host.example/v1'}
    response = creative['client'].put('/api/settings', json=change)
    assert response.status_code == 400 and creative['settings_path'].read_bytes() == previous
    assert SECRET not in response.text
    # Explicitly clearing acknowledges the new destination; environment key
    # remains bound to the original configured destination.
    monkeypatch.setenv('SEEDREAM_API_KEY', SECRET)
    response = creative['client'].put('/api/settings', json={**change, 'api_key': ''})
    assert response.status_code == 200
    provider = selected(response.json())
    assert not provider['stored_credential'] and not provider['platform_credential'] and not provider['available']
    response, _ = submit(creative, mode='platform')
    assert response.status_code == 400 and not creative['adapter'].calls
    response = creative['client'].put('/api/settings', json={**change, 'api_key': 'fresh-host-key'})
    assert response.status_code == 200
    response, _ = submit(creative)
    assert response.status_code == 202, response.text
    assert wait_job(creative, response.json()['job'])['job']['status'] == 'succeeded'
    assert creative['adapter'].calls[0][1] == 'fresh-host-key'


def test_stale_settings_consent_rejected_and_active_job_keeps_snapshot(creative):
    setup_key(creative)
    old_consent = payload(creative, colors=[])
    change = {'provider': 'seedream', 'base_url': 'https://second.example', 'model': 'second-model', 'api_key': 'second-key'}
    assert creative['client'].put('/api/settings', json=change).status_code == 200
    url = f"/api/projects/{creative['project']['id']}/generation"
    response = creative['client'].post(url, json=old_consent)
    assert response.status_code == 409 and not creative['adapter'].calls
    creative['adapter'].release.clear()
    response, _ = submit(creative)
    assert response.status_code == 202, response.text
    assert creative['adapter'].started.wait(3)
    assert creative['client'].put('/api/settings', json={**change, 'model': 'third-model', 'api_key': 'third-key'}).status_code == 200
    creative['adapter'].release.set()
    assert wait_job(creative, response.json()['job'])['job']['status'] == 'succeeded'
    sent, credential = creative['adapter'].calls[0]
    assert sent.model == 'second-model' and credential == 'second-key'


def test_missing_settings_consent_revision_rejected_before_dispatch(creative):
    setup_key(creative)
    data = payload(creative, colors=[])
    del data['settings_revision']
    response = creative['client'].post(f"/api/projects/{creative['project']['id']}/generation", json=data)
    assert response.status_code == 409 and not creative['adapter'].calls


def test_legacy_config_supplies_new_presets_without_rewriting(tmp_path):
    data = json.loads((ROOT / 'config/providers.json').read_text(encoding='utf-8'))
    data['providers'] = [p for p in data['providers'] if p['id'] in ('seedream', 'qwen')]
    path = tmp_path / 'providers.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    old = path.read_bytes()
    config = load_provider_config(path, environ={})
    assert {p.id for p in config.providers} == set(ProviderId)
    assert config.provider(ProviderId.OPENROUTER).base_url == 'https://openrouter.ai/api/v1/images'
    assert path.read_bytes() == old


@pytest.mark.parametrize('provider,protocol,size', [('custom', 'images_generations_json', '1024x1024'), ('openrouter', 'openrouter_images', '1K')])
def test_generation_export_provenance_excludes_private_settings(creative, provider, protocol, size):
    response = creative['client'].put('/api/settings', json={'provider': provider, 'api_key': SECRET, 'default_provider': provider, 'protocol': protocol})
    assert response.status_code == 200, response.text
    response, _ = submit(creative, provider=provider, size=size)
    assert response.status_code == 202, response.text
    result = wait_job(creative, response.json()['job'])
    assert result['job']['status'] == 'succeeded'
    url = f"/api/projects/{creative['project']['id']}"
    artwork = creative['client'].get(url + '/creative').json()['generations'][0]
    response = creative['client'].post(url + '/creative/exports', json={'revision': result['project']['revision'], 'artwork_id': artwork['id'], 'format': 'zip'})
    assert response.status_code == 200
    exported = response.json()['export']
    content = (creative['output'] / creative['project']['id'] / exported['id'] / exported['filename']).read_bytes()
    with ZipFile(BytesIO(content)) as archive:
        assert not any('.private' in name or 'provider-settings' in name for name in archive.namelist())
        settings = json.loads(archive.read('creative-settings.json'))
        assert settings['protocol'] == protocol
        assert all(SECRET.encode() not in archive.read(name) for name in archive.namelist())
    record = creative['repository'].load(creative['project']['id'])
    assert record.generations[0].provider == provider
    assert SECRET not in record.model_dump_json()
