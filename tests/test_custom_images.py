"""Exact wire contracts and bounded, credential-safe image responses."""
import base64
from email.parser import BytesParser
from io import BytesIO
import json

import httpx
from PIL import Image
from pydantic import SecretStr
import pytest

from pattern_reborn.generation.base import CustomProtocol, FailureKind, GenerationFailure, ProviderId
from pattern_reborn.generation.custom import CustomImageAdapter
from pattern_reborn.generation.openrouter_catalog import CATALOG_URL, image_models
from tests.test_generation_base import make_generation_request, reference_png  # noqa: F401


def png_bytes():
    stream = BytesIO()
    Image.new('RGB', (16, 12), 'green').save(stream, format='PNG')
    return stream.getvalue()


@pytest.mark.parametrize('protocol,provider', [
    (CustomProtocol.OPENAI_IMAGES_EDITS, ProviderId.CUSTOM),
    (CustomProtocol.IMAGES_GENERATIONS_JSON, ProviderId.CUSTOM),
    (CustomProtocol.OPENROUTER_IMAGES, ProviderId.OPENROUTER),
])
def test_exact_full_endpoint_and_one_reference(protocol, provider, reference_png, tmp_path, respx_mock):
    endpoint = 'https://thirdparty.example/prefix/custom-image-route'
    image = png_bytes()
    route = respx_mock.post(endpoint).respond(json={'data': [{'b64_json': base64.b64encode(image).decode()}]})
    request = make_generation_request(reference_png, provider=provider, model='vendor/image-model')
    adapter = CustomImageAdapter(httpx.Client(), endpoint, tmp_path, protocol, provider)
    result = adapter.generate(request, SecretStr('do-not-leak-credential'))
    assert len(route.calls) == 1 and len(result.local_files) == 1
    assert Image.open(result.local_files[0]).size == (16, 12)
    sent = route.calls[0].request
    assert sent.headers['authorization'] == 'Bearer do-not-leak-credential'
    assert sent.extensions['timeout']['read'] == 180.0
    if protocol is CustomProtocol.OPENAI_IMAGES_EDITS:
        header = sent.headers['content-type']
        assert header.startswith('multipart/form-data; boundary=')
        message = BytesParser().parsebytes(f'Content-Type: {header}\r\nMIME-Version: 1.0\r\n\r\n'.encode() + sent.content)
        fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True) for part in message.walk() if part.get_content_disposition() == 'form-data'}
        assert fields == {'image': reference_png.read_bytes(), 'model': b'vendor/image-model',
                          'prompt': request.prompt.encode(), 'size': b'1024x1024', 'n': b'1'}
    else:
        payload = json.loads(sent.content)
        assert payload['model'] == 'vendor/image-model' and payload['n'] == 1
        if protocol is CustomProtocol.OPENROUTER_IMAGES:
            assert set(payload) == {'model', 'prompt', 'size', 'n', 'input_references', 'output_format'}
            assert payload['output_format'] == 'png'
            value = payload['input_references'][0]['image_url']['url']
        else:
            assert set(payload) == {'model', 'prompt', 'size', 'n', 'image'}
            value = payload['image']
        assert base64.b64decode(value.split(',')[1]) == reference_png.read_bytes()
    assert 'do-not-leak-credential' not in result.model_dump_json()


def test_download_does_not_forward_key_or_follow_redirect(reference_png, tmp_path, respx_mock):
    endpoint = 'https://thirdparty.example/image'
    remote = 'https://cdn.example/result.png'
    respx_mock.post(endpoint).respond(json={'data': [{'url': remote}]})
    route = respx_mock.get(remote).respond(content=png_bytes(), headers={'content-type': 'image/png'})
    adapter = CustomImageAdapter(httpx.Client(), endpoint, tmp_path, CustomProtocol.IMAGES_GENERATIONS_JSON)
    adapter.generate(make_generation_request(reference_png, provider=ProviderId.CUSTOM), SecretStr('private-key'))
    assert 'authorization' not in route.calls[0].request.headers
    route.respond(status_code=302, headers={'location': 'https://elsewhere.example/secret'})
    with pytest.raises(GenerationFailure):
        adapter.generate(make_generation_request(reference_png, provider=ProviderId.CUSTOM), SecretStr('private-key'))
    assert len(respx_mock.calls) == 4


@pytest.mark.parametrize('body', [{}, {'data': []}, {'data': [{'revised_prompt': 'text only'}]}, {'data': [{'b64_json': 'not-image'}]}, {'data': [{}, {}]}])
def test_malformed_response_never_persists_or_retries(body, reference_png, tmp_path, respx_mock):
    endpoint = 'https://thirdparty.example/image'
    route = respx_mock.post(endpoint).respond(json=body)
    adapter = CustomImageAdapter(httpx.Client(), endpoint, tmp_path, CustomProtocol.IMAGES_GENERATIONS_JSON)
    with pytest.raises(GenerationFailure) as failure:
        adapter.generate(make_generation_request(reference_png, provider=ProviderId.CUSTOM), SecretStr('private-key'))
    assert failure.value.kind is FailureKind.MALFORMED and len(route.calls) == 1
    assert list(tmp_path.glob('custom-*.png')) == []


def test_bounded_response_and_http_error_redact_remote_body(reference_png, tmp_path, respx_mock, monkeypatch):
    import pattern_reborn.generation.http as helpers
    endpoint = 'https://thirdparty.example/image'
    route = respx_mock.post(endpoint).respond(status_code=401, text='Authorization Bearer private-key')
    adapter = CustomImageAdapter(httpx.Client(), endpoint, tmp_path, CustomProtocol.IMAGES_GENERATIONS_JSON)
    with pytest.raises(GenerationFailure) as failure:
        adapter.generate(make_generation_request(reference_png, provider=ProviderId.CUSTOM), SecretStr('private-key'))
    assert failure.value.kind is FailureKind.AUTH and 'private-key' not in str(failure.value)
    monkeypatch.setattr(helpers, 'MAX_RESPONSE_BYTES', 32)
    route.respond(content=b'x' * 33)
    with pytest.raises(GenerationFailure) as failure:
        adapter.generate(make_generation_request(reference_png, provider=ProviderId.CUSTOM), SecretStr('private-key'))
    assert failure.value.kind is FailureKind.MALFORMED


def test_large_image_rejected_before_pixel_decode(tmp_path, monkeypatch):
    import struct
    import zlib
    from pattern_reborn.generation.http import persist_generated_png
    image = bytearray(png_bytes())
    # Rewrite IHDR dimensions/CRC without allocating an oversized image.
    image[16:24] = struct.pack('>II', 5000, 5000)
    image[29:33] = struct.pack('>I', zlib.crc32(image[12:29]))
    def forbid_decode(self, *args, **kwargs):
        pytest.fail('Oversized image must be rejected before load')
    monkeypatch.setattr(Image.Image, 'load', forbid_decode)
    with pytest.raises(GenerationFailure) as failure:
        persist_generated_png(bytes(image), tmp_path, 'oversized')
    assert failure.value.kind is FailureKind.MALFORMED
    assert not list(tmp_path.iterdir())


def test_public_catalog_filters_incompatible_models_without_credentials(respx_mock):
    def model(identifier, inputs=('text', 'image'), outputs=('image',), minimum=0, maximum=4):
        return {'id': identifier, 'name': identifier, 'architecture': {'input_modalities': list(inputs), 'output_modalities': list(outputs)},
                'supported_parameters': {'input_references': {'min': minimum, 'max': maximum}, 'resolution': {'values': ['1K', '1.5K', '2K', 'bad-size']}}}
    route = respx_mock.get(CATALOG_URL).respond(json={'data': [model('vendor/edit'), model('vendor/text', outputs=('text',)),
        model('vendor/no-reference', inputs=('text',)), model('vendor/two-reference', minimum=2), model('vendor/zero', maximum=0)]})
    result = image_models(httpx.Client())
    assert result == [{'id': 'vendor/edit', 'name': 'vendor/edit', 'size_options': ['1K', '1.5K', '2K']}]
    assert 'authorization' not in route.calls[0].request.headers
    assert not route.calls[0].request.content
