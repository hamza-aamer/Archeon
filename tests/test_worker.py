import threading

import pytest

from archeon import worker as worker_module
from archeon.pipeline.base import Cancelled, Stage, StageError
from archeon.worker import run_scene, scene_layout


def make_stages(calls, fail_at=None, cancel_at=None):
    def stage(key):
        def run(ctx):
            calls.append(key)
            ctx.progress(0.5)
            if key == fail_at:
                raise StageError(f"{key} exploded")
            if key == cancel_at:
                raise Cancelled()
            ctx.stats[f"{key}_ran"] = True
            if key == "export":
                ctx.artifacts["thumbnail"] = "thumbnail.jpg"
        return Stage(key, key.title(), 1, run)
    return [stage(k) for k in ("frames", "colmap", "export")]


@pytest.fixture
def scene(store, settings):
    created = store.create("Test", "preview")
    scene_layout(settings, created["id"]).root.mkdir(parents=True)
    return created


def test_runs_all_stages(store, settings, scene, monkeypatch):
    calls = []
    monkeypatch.setattr(worker_module, "stages_for", lambda preset: make_stages(calls))
    assert run_scene(store, settings, scene["id"]) == "done"
    final = store.get(scene["id"])
    assert calls == ["frames", "colmap", "export"]
    assert final["status"] == "done" and final["progress"] == 1.0
    assert final["artifacts"] == {"thumbnail": "thumbnail.jpg"}
    assert final["stats"]["colmap_ran"] is True
    assert set(final["stage_times"]) == {"frames", "colmap", "export"}


def test_failure_then_resume_skips_finished_stages(store, settings, scene, monkeypatch):
    calls = []
    monkeypatch.setattr(worker_module, "stages_for", lambda preset: make_stages(calls, fail_at="colmap"))
    assert run_scene(store, settings, scene["id"]) == "failed"
    failed = store.get(scene["id"])
    assert failed["error"] == "colmap exploded" and failed["stage"] == "colmap"
    assert "colmap exploded" in scene_layout(settings, scene["id"]).log.read_text()

    calls.clear()
    monkeypatch.setattr(worker_module, "stages_for", lambda preset: make_stages(calls))
    assert run_scene(store, settings, scene["id"]) == "done"
    assert calls == ["colmap", "export"]
    assert store.get(scene["id"])["error"] is None


def test_cancel_and_shutdown_statuses(store, settings, scene, monkeypatch):
    monkeypatch.setattr(worker_module, "stages_for", lambda preset: make_stages([], cancel_at="colmap"))
    assert run_scene(store, settings, scene["id"]) == "cancelled"
    shutdown = threading.Event()
    shutdown.set()
    assert run_scene(store, settings, scene["id"], shutdown_event=shutdown) == "interrupted"


def test_unexpected_exception_is_reported(store, settings, scene, monkeypatch):
    def boom(ctx):
        raise ValueError("bug")
    monkeypatch.setattr(worker_module, "stages_for", lambda preset: [Stage("frames", "Frames", 1, boom)])
    assert run_scene(store, settings, scene["id"]) == "failed"
    assert store.get(scene["id"])["error"] == "Unexpected error: bug"
    assert "Traceback" in scene_layout(settings, scene["id"]).log.read_text()


def test_mark_interrupted(store):
    running = store.create("A", "preview", status="running")
    uploading = store.create("B", "preview", status="uploading")
    assert store.mark_interrupted() == 1
    assert store.get(running["id"])["status"] == "interrupted"
    assert store.get(uploading["id"])["status"] == "failed"
