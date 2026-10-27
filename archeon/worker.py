"""Runs queued scenes through the pipeline, one at a time (a single GPU cannot train two scenes at once)."""

from __future__ import annotations

import shutil
import threading
import time
import traceback
from typing import Optional

from .config import Settings
from .db import SceneStore
from .pipeline import Cancelled, SceneLayout, StageContext, StageError, stages_for
from .presets import PRESETS


def scene_layout(settings: Settings, scene_id: str) -> SceneLayout:
    return SceneLayout(settings.scenes_dir / scene_id)


def run_scene(store: SceneStore, settings: Settings, scene_id: str,
              cancel_event: Optional[threading.Event] = None,
              shutdown_event: Optional[threading.Event] = None) -> str:
    """Run (or resume) every remaining stage of a scene. Returns the final status."""
    cancel_event = cancel_event or threading.Event()
    scene = store.get(scene_id)
    preset = PRESETS[scene["preset"]]
    layout = scene_layout(settings, scene_id)
    layout.work.mkdir(parents=True, exist_ok=True)
    stages = stages_for(preset)
    total_weight = sum(stage.weight for stage in stages)
    stats, stage_times, artifacts = scene["stats"], scene["stage_times"], scene["artifacts"]

    store.update(scene_id, status="running", started_at=time.time(), finished_at=None, error=None)
    done_weight = 0.0
    try:
        for stage in stages:
            marker = layout.done_marker(stage.key)
            if marker.exists():
                done_weight += stage.weight
                continue
            store.update(scene_id, stage=stage.key, stage_started_at=time.time(), stage_progress=0.0,
                         progress=done_weight / total_weight)
            last_write = [0.0]

            def on_progress(fraction: float, weight=stage.weight, base=done_weight) -> None:
                now = time.monotonic()
                if now - last_write[0] >= 0.5 or fraction >= 1.0:
                    last_write[0] = now
                    store.update(scene_id, stage_progress=fraction, progress=(base + weight * fraction) / total_weight)

            ctx = StageContext(settings, layout, preset, cancel_event=cancel_event, on_progress=on_progress,
                               stats=stats, artifacts=artifacts)
            ctx.log(f"===== {stage.label} =====")
            started = time.time()
            stage.run(ctx)
            stage_times[stage.key] = round(time.time() - started, 1)
            marker.touch()
            done_weight += stage.weight
            ctx.log(f"{stage.label}: done in {stage_times[stage.key]:.0f} s")
            store.update(scene_id, stats=stats, stage_times=stage_times, artifacts=artifacts,
                         stage_progress=1.0, progress=done_weight / total_weight)

        store.update(scene_id, status="done", stage=None, progress=1.0, finished_at=time.time(),
                     artifacts=artifacts)
        return "done"
    except Cancelled:
        status = "interrupted" if shutdown_event is not None and shutdown_event.is_set() else "cancelled"
        _log(layout, f"{status} by request")
        store.update(scene_id, status=status, finished_at=time.time(),
                     error="Server stopped while this scene was processing." if status == "interrupted" else None)
        return status
    except StageError as exc:
        _log(layout, f"FAILED: {exc}")
        store.update(scene_id, status="failed", error=str(exc), finished_at=time.time())
        return "failed"
    except Exception as exc:  # unexpected bug: keep the traceback in the scene log
        _log(layout, "FAILED with an unexpected error:\n" + traceback.format_exc())
        store.update(scene_id, status="failed", error=f"Unexpected error: {exc}", finished_at=time.time())
        return "failed"
    finally:
        store.update(scene_id, stats=stats, stage_times=stage_times)


def _log(layout: SceneLayout, message: str) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    with open(layout.log, "a", encoding="utf-8") as fh:
        fh.write(f"[archeon] {message}\n")


class Worker:
    """Background thread that drains the queue."""

    def __init__(self, store: SceneStore, settings: Settings):
        self.store = store
        self.settings = settings
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._lock = threading.Lock()
        self._current: Optional[tuple[str, threading.Event]] = None
        self._thread = threading.Thread(target=self._loop, name="archeon-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    @property
    def current_scene(self) -> Optional[str]:
        with self._lock:
            return self._current[0] if self._current else None

    def cancel(self, scene_id: str) -> None:
        with self._lock:
            if self._current and self._current[0] == scene_id:
                self._current[1].set()
                return
        scene = self.store.get(scene_id)
        if scene and scene["status"] == "queued":
            self.store.update(scene_id, status="cancelled", finished_at=time.time())

    def wait_until_idle(self, scene_id: str, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while self.current_scene == scene_id and time.monotonic() < deadline:
            time.sleep(0.2)

    def delete(self, scene_id: str) -> None:
        self.cancel(scene_id)
        self.wait_until_idle(scene_id)
        shutil.rmtree(scene_layout(self.settings, scene_id).root, ignore_errors=True)
        self.store.delete(scene_id)

    def stop(self) -> None:
        self._shutdown.set()
        with self._lock:
            if self._current:
                self._current[1].set()
        self._wake.set()
        self._thread.join(timeout=30)

    def _loop(self) -> None:
        while not self._shutdown.is_set():
            scene = self.store.next_queued()
            if scene is None:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
                continue
            cancel_event = threading.Event()
            with self._lock:
                self._current = (scene["id"], cancel_event)
            try:
                run_scene(self.store, self.settings, scene["id"], cancel_event, self._shutdown)
            finally:
                with self._lock:
                    self._current = None
