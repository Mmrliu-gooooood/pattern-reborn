"""Persisted composition, palette and downloadable snapshot integration."""
import base64
from io import BytesIO
import json
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image
from tests.test_web_api import upload, edit, HEADERS
from pattern_reborn.web_api import create_app
from pattern_reborn.web_design import recolor
from pattern_reborn.projects import ProjectRepository
from fastapi.testclient import TestClient

@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('PATTERN_REBORN_OUTPUTS', str(tmp_path / 'outputs'))
    workspace = tmp_path / 'projects'
    with TestClient(create_app(workspace, settings_path=workspace.parent / 'private/settings.json'), headers=HEADERS) as client:
        project, original = upload(client)
        path = f'/api/projects/{project["id"]}'
        response = client.post(path+'/save', json=edit(project))
        assert response.status_code == 200, response.text
        yield client, response.json(), path, workspace, original

@pytest.mark.parametrize('layout', ['mirror','rotation','radial','border','two_way','four_way'])
def test_composition_roundtrip_and_snapshot(studio, layout):
    client, project, path, workspace, original = studio
    context = client.get(path+'/design').json()
    settings = {**context['settings'], 'width':256, 'height':192, 'layout':layout, 'scale':0.24,
                'colors':{context['palette'][0]:'#28664A'}}
    data = {'revision':project['revision'], 'settings':settings}
    preview = client.post(path+'/design/preview', json=data)
    assert preview.status_code == 200, preview.text
    expected = Image.open(BytesIO(base64.b64decode(preview.json()['image'].split(',')[1])))
    saved = client.post(path+'/design/save',json=data)
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert saved['has_pattern']
    assert client.post(path+'/design/save',json=data).status_code == 409
    with TestClient(create_app(workspace, settings_path=workspace.parent / 'private/settings.json'), headers=HEADERS) as reopened:
        assert reopened.get(path+'/design').json()['settings'] == settings
        response = reopened.post(path+'/exports',json={'revision':saved['revision'],'format':'png','source':'pattern'})
        assert response.status_code == 200, response.text
        exported = response.json()
        png = reopened.get(exported['export']['url'])
        actual = Image.open(BytesIO(png.content))
        assert actual.size == (256,192)
        np.testing.assert_array_equal(actual,expected)
        record = ProjectRepository(workspace).load(project['id'])
        assert (ProjectRepository(workspace).project_dir(record.id)/record.source.relative_path).read_bytes() == original
        # Re-extraction invalidates the current composition, but historical export is immutable.
        new = reopened.post(path+'/save',json=edit(exported['project'])).json()
        assert not new['has_pattern']
        assert reopened.post(path+'/exports',json={'revision':new['revision'],'format':'png','source':'pattern'}).status_code == 400
        assert reopened.get(exported['export']['url']).content == png.content
        assert reopened.get(path+'/exports/unknown').status_code == 404


def test_bundle_source_selection_and_provenance(studio):
    client, project, path, workspace, original = studio
    for include in (False,True):
        response = client.post(path+'/exports',json={'revision':project['revision'],'source':'result','format':'zip','include_original':include})
        assert response.status_code == 200, response.text
        result = response.json(); project = result['project']
        with ZipFile(BytesIO(client.get(result['export']['url']).content)) as archive:
            names = archive.namelist()
            assert 'workspace-settings.json' in names
            metadata = json.loads(archive.read('workspace-settings.json'))
            assert metadata['source_sha256'] == project['source_sha256']
            assert metadata['edit']['feather'] == 3
            sources = [name for name in names if name.startswith('source/')]
            assert bool(sources) == include
            if include: assert archive.read(sources[0]) == original


def test_design_bounds_and_svg_failure(studio,monkeypatch):
    client, project, path, *_ = studio
    data={'revision':project['revision'],'settings':{'width':999999}}
    assert client.post(path+'/design/preview',json=data).status_code == 422
    data['settings']={'colors':{'#000000':'#BAD'}}
    assert client.post(path+'/design/preview',json=data).status_code == 422
    from pattern_reborn.vectorize import VectorResult
    monkeypatch.setattr('pattern_reborn.web_api.Vectorizer.vectorize',lambda *a: VectorResult(False,'测试：矢量不可用'))
    response=client.post(path+'/exports',json={'revision':project['revision'],'source':'result','format':'svg'})
    assert response.status_code == 400 and '矢量不可用' in response.json()['detail']
    assert client.get(path).json()['revision'] == project['revision']


def test_palette_shift_keeps_texture_alpha_and_other_groups():
    pixels=np.array([[[100,30,20,50],[110,40,30,200],[20,80,150,255]]],dtype=np.uint8)
    result=np.asarray(recolor(Image.fromarray(pixels),['#641E14','#145096'],{'#641E14':'#326432'}))
    assert result[0,0].tolist()==[50,100,50,50]
    assert result[0,1].tolist()==[60,110,60,200]
    assert result[0,2].tolist()==pixels[0,2].tolist()

