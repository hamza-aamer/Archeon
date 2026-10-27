import pytest
from fastapi.testclient import TestClient

from archeon.api import create_app
from archeon.worker import scene_layout


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, start_worker=False)) as test_client:
        yield test_client


def upload(client, name="Kitchen", preset="preview", filename="walk.mp4", data=b"fake video bytes"):
    return client.post("/api/scenes", files={"video": (filename, data, "video/mp4")},
                       data={"name": name, "preset": preset})


def test_index_and_static(client):
    assert "Archeon" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/vendor/gaussian-splats-3d/gaussian-splats-3d.module.js").status_code == 200


def test_presets_and_health(client):
    presets = client.get("/api/presets").json()
    assert presets["default"] == "standard"
    assert {p["name"] for p in presets["presets"]} == {"preview", "standard", "high"}
    checks = {c["name"]: c for c in client.get("/api/health").json()["checks"]}
    assert checks["COLMAP"]["ok"] is False  # the test settings have no tools configured


def test_upload_lifecycle(client, settings):
    response = upload(client)
    assert response.status_code == 201
    scene = response.json()
    assert scene["status"] == "queued" and scene["name"] == "Kitchen"
    assert [s["key"] for s in scene["stages"]] == ["frames", "colmap", "gaussians", "export"]
    video = scene_layout(settings, scene["id"]).video
    assert video.name == "video.mp4" and video.read_bytes() == b"fake video bytes"

    assert [s["id"] for s in client.get("/api/scenes").json()] == [scene["id"]]
    assert client.get(f"/api/scenes/{scene['id']}/log").json() == {"text": "", "offset": 0}

    renamed = client.patch(f"/api/scenes/{scene['id']}", data={"name": "Kitchen v2"}).json()
    assert renamed["name"] == "Kitchen v2"

    assert client.post(f"/api/scenes/{scene['id']}/retry").status_code == 409
    assert client.post(f"/api/scenes/{scene['id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/scenes/{scene['id']}/cancel").status_code == 409
    assert client.post(f"/api/scenes/{scene['id']}/retry").json()["status"] == "queued"

    assert client.delete(f"/api/scenes/{scene['id']}").status_code == 204
    assert client.get(f"/api/scenes/{scene['id']}").status_code == 404
    assert not scene_layout(settings, scene["id"]).root.exists()


def test_log_offsets(client, settings):
    scene = upload(client).json()
    scene_layout(settings, scene["id"]).log.write_text("hello\n")
    first = client.get(f"/api/scenes/{scene['id']}/log").json()
    assert first == {"text": "hello\n", "offset": 6}
    assert client.get(f"/api/scenes/{scene['id']}/log", params={"offset": 6}).json() == {"text": "", "offset": 6}


def test_upload_validation(client, store):
    assert upload(client, preset="ultra").status_code == 400
    assert upload(client, filename="notes.txt").status_code == 400
    assert upload(client, data=b"").status_code == 400
    assert upload(client, data=b"x" * (1024 * 1024 + 1)).status_code == 413
    assert store.list() == []  # rejected uploads leave nothing behind


def test_files_only_serves_listed_artifacts(client, settings, store):
    scene = store.create("Done", "preview", status="done")
    artifacts = scene_layout(settings, scene["id"]).artifacts
    artifacts.mkdir(parents=True)
    (artifacts / "scene.splat").write_bytes(b"\x00" * 32)
    (artifacts / "secret.txt").write_text("nope")
    store.update(scene["id"], artifacts={"scene_splat": "scene.splat"})

    body = client.get(f"/api/scenes/{scene['id']}").json()
    assert body["files"] == {"scene_splat": f"/api/scenes/{scene['id']}/files/scene.splat"}
    response = client.get(body["files"]["scene_splat"])
    assert response.status_code == 200 and len(response.content) == 32
    assert "attachment" in response.headers["content-disposition"]
    assert client.get(f"/api/scenes/{scene['id']}/files/secret.txt").status_code == 404
    assert client.get(f"/api/scenes/{scene['id']}/files/..%2Farchive.db").status_code == 404
    assert client.get("/api/scenes/not-an-id").status_code == 404


def test_pipeline_and_storage(client, settings, store):
    stages = client.get("/api/pipeline").json()
    assert [s["key"] for s in stages][:3] == ["frames", "colmap", "gaussians"]
    assert next(s for s in stages if s["key"] == "sugar_mesh")["presets"] == ["standard", "high"]

    scene = upload(client).json()
    work = scene_layout(settings, scene["id"]).work
    work.mkdir(parents=True)
    (work / "big.bin").write_bytes(b"x" * 1000)
    row = next(r for r in client.get("/api/storage").json()["scenes"] if r["id"] == scene["id"])
    assert row["work"] == 1000 and row["video"] == len(b"fake video bytes")


def test_clean_keeps_previews(client, settings, store):
    scene = store.create("Done", "preview", status="done")
    work = scene_layout(settings, scene["id"]).work
    (work / "thumbs").mkdir(parents=True)
    (work / "thumbs" / "frame_00001.jpg").write_bytes(b"jpg")
    (work / "reconstruction.json").write_text("{}")
    (work / "output").mkdir()
    (work / "output" / "checkpoint.pt").write_bytes(b"x" * 500)

    assert client.post(f"/api/scenes/{scene['id']}/clean").json() == {"freed": 500}
    assert sorted(p.name for p in work.iterdir()) == ["reconstruction.json", "thumbs"]
    queued = upload(client).json()
    assert client.post(f"/api/scenes/{queued['id']}/clean").status_code == 409


def test_thumbnail_upload_once(client, store):
    scene = store.create("Imported", "imported", status="done")
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    files = {"image": ("t.jpg", jpeg, "image/jpeg")}
    assert client.post(f"/api/scenes/{scene['id']}/thumbnail", files={"image": ("t.png", b"PNG", "image/png")}).status_code == 400
    body = client.post(f"/api/scenes/{scene['id']}/thumbnail", files=files).json()
    assert body["files"]["thumbnail"].endswith("/files/thumbnail.jpg")
    assert client.get(body["files"]["thumbnail"]).content == jpeg
    assert client.post(f"/api/scenes/{scene['id']}/thumbnail", files=files).status_code == 409
