"""Exercise the local web boundary and persisted editing round trip."""
import base64
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from pattern_reborn.web_api import create_app
from pattern_reborn.projects import ProjectRepository

HEADERS = {"X-Pattern-Reborn": "local-workspace"}


def test_link_navigation_allows_app_shell_but_not_project_data(client):
    response = client.get("/", headers={"sec-fetch-site": "cross-site"})
    assert response.status_code != 403
    assert client.get("/api/library", headers={"sec-fetch-site": "cross-site"}).status_code == 403


def test_active_generation_guards_mutations_without_blocking_reads(client):
    from types import SimpleNamespace
    project, _ = upload(client)
    path = f'/api/projects/{project["id"]}'
    client.app.state.creative["jobs"]["pending"] = SimpleNamespace(project_id=project["id"], status="running")
    assert client.patch(path, json={"revision": project["revision"], "name": "changed"}).status_code == 409
    assert client.post(path + "/save", json=edit(project)).status_code == 409
    assert client.post(path + "/exports", json={"revision": project["revision"], "source": "result"}).status_code == 409
    assert client.get(path).json()["revision"] == project["revision"]
    assert client.get(path + "/backup").status_code == 200
    client.app.state.creative["jobs"]["pending"].status = "cancelled"
    assert client.post(path + "/save", json=edit(project)).status_code == 200


def test_after_snapshot_failure_reports_saved_revision(workspace, monkeypatch):
    import pattern_reborn.web_api as module
    register = module.register_project_routes
    def failing_snapshot(*args, **kwargs):
        original = register(*args, **kwargs)
        def capture(project, label):
            if label == "提取保存":
                raise OSError("disk full")
            return original(project, label)
        return capture
    monkeypatch.setattr(module, "register_project_routes", failing_snapshot)
    with TestClient(module.create_app(workspace, settings_path=workspace.parent / 'private/settings.json'), headers=HEADERS) as client:
        project, _ = upload(client)
        path = f'/api/projects/{project["id"]}'
        response = client.post(path + "/save", json=edit(project))
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["has_result"] and saved["revision"] != project["revision"]
        assert any("版本备份未完成" in warning for warning in saved["warnings"])
        assert client.get(path).json()["revision"] == saved["revision"]


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "projects"


@pytest.fixture
def client(workspace):
    with TestClient(create_app(workspace, settings_path=workspace.parent / 'private/settings.json'), headers=HEADERS) as client:
        yield client


def upload(client):
    image = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
    ImageDraw.Draw(image).rectangle((24, 24, 100, 100), fill=(190, 30, 35, 180))
    stream = BytesIO()
    image.save(stream, format="PNG")
    response = client.post("/api/projects", data={"name": "测试纹样", "category": "paper_cutting"}, files={"file": ("original.png", stream.getvalue(), "image/png")})
    assert response.status_code == 200, response.text
    return response.json(), stream.getvalue()


def edit(project, **overrides):
    return {"revision": project["revision"], "profile": "silhouette", "box": [4, 4, 124, 124], "strokes": [{"mode": "remove", "points": [[60, 60]], "width": 18}], "feather": 3, **overrides}


def test_upload_edit_save_reopen_download_preserves_original(client, workspace):
    project, original = upload(client)
    path = f'/api/projects/{project["id"]}'
    data = edit(project)
    preview = client.post(path + "/preview", json=data)
    assert preview.status_code == 200, preview.text
    expected = np.asarray(Image.open(BytesIO(base64.b64decode(preview.json()["result"].split(",")[1]))))
    assert not preview.json()["empty"]
    assert expected[:, :, 3].max() == 180  # Preserve partial source alpha.
    assert expected[60, 60, 3] < expected[40, 40, 3]
    assert np.any((expected[:, :, 3] > 0) & (expected[:, :, 3] < 180))
    response = client.post(path + "/save", json=data)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["has_result"] and saved["revision"] != project["revision"]
    with TestClient(create_app(workspace, settings_path=workspace.parent / 'private/settings.json'), headers=HEADERS) as reopened:
        detail = reopened.get(path).json()
        assert {k: detail["draft"][k] for k in data if k != "revision"} == {k: v for k, v in data.items() if k != "revision"}
        assert detail["draft"]["extraction"]["mode"] == "auto"
        download = reopened.get(path + "/image?kind=result&download=true")
        assert "attachment" in download.headers["content-disposition"]
        assert np.array_equal(expected, np.asarray(Image.open(BytesIO(download.content))))
        mask = np.asarray(Image.open(BytesIO(reopened.get(path + "/image?kind=mask").content)))
        assert set(np.unique(mask)) <= {0, 255}
    repository = ProjectRepository(workspace)
    record = repository.load(project["id"])
    assert (repository.project_dir(record.id) / record.source.relative_path).read_bytes() == original
    assert record.schema_version == 1


def test_rename_archive_restore_and_conflicting_revision(client):
    project, _ = upload(client)
    path = f'/api/projects/{project["id"]}'
    renamed = client.patch(path, json={"revision": project["revision"], "name": "牡丹习作", "archived": True}).json()
    assert renamed["name"] == "牡丹习作" and renamed["archived"]
    assert client.get("/api/library").json()["projects"][0]["archived"]
    assert client.post(path + "/save", json=edit(project)).status_code == 409
    restored = client.patch(path, json={"revision": renamed["revision"], "archived": False})
    assert restored.status_code == 200 and not restored.json()["archived"]


@pytest.mark.parametrize("patch,status", [({"box": [-1, 0, 50, 50]}, 400), ({"box": [0, 0, 0, 0]}, 400), ({"strokes": [{"mode": "keep", "points": [[128, 1]], "width": 4}]}, 400), ({"feather": 11}, 422), ({"box": [True, 0, 50, 50]}, 422), ({"profile": "unknown"}, 422)])
def test_reject_invalid_editor_coordinates(client, patch, status):
    project, _ = upload(client)
    response = client.post(f'/api/projects/{project["id"]}/preview', json=edit(project, **patch))
    assert response.status_code == status


def test_local_only_boundary_and_image_validation(client):
    assert client.post("/api/examples/peony-embroidery/open", headers={"X-Pattern-Reborn": ""}).status_code == 403
    assert client.get("/api/library", headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get("/api/library", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/library", headers={"Host": "example.com"}).status_code == 400
    response = client.post("/api/projects", data={"name": "bad", "category": "paper_cutting"}, files={"file": ("bad.png", b"not an image", "image/png")})
    assert response.status_code == 400
    assert client.get("/api/library").json()["projects"] == []


def test_examples_are_not_projects_until_opened(client):
    library = client.get("/api/library").json()
    assert len(library["examples"]) == 6 and not library["projects"]
    first = client.post("/api/examples/peony-embroidery/open").json()
    second = client.post("/api/examples/peony-embroidery/open").json()
    assert first["id"] == second["id"]
    assert first["rights"]["license"] == "CC0 / The Met Open Access"
    assert first["provenance"] == "traditional_reference"
