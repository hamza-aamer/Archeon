"""HTTP API and web UI."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import REPO_ROOT, Settings, get_settings
from .db import ACTIVE_STATUSES, SceneStore
from .doctor import gpu_stats, run_checks
from .pipeline import STAGES, stages_for
from .presets import DEFAULT_PRESET, PRESETS
from .worker import Worker, scene_layout

WEB_DIR = REPO_ROOT / "web"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"}
RETRYABLE = ("failed", "cancelled", "interrupted")
_SCENE_ID = re.compile(r"^[0-9a-f]{12}$")
_FRAME_NAME = re.compile(r"^frame_\d{5}\.jpg$")


def create_app(settings: Optional[Settings] = None, start_worker: bool = True) -> FastAPI:
    settings = settings or get_settings()
    store = SceneStore(settings.db_path)
    worker = Worker(store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.mark_interrupted()
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()

    app = FastAPI(title="Archeon", version=__version__, lifespan=lifespan)
    app.state.store, app.state.worker, app.state.settings = store, worker, settings

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        # The UI has no build step or hashed filenames, so make browsers revalidate instead of caching blindly.
        response = await call_next(request)
        if request.url.path.startswith("/static/") and not request.url.path.startswith("/static/vendor/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def present(scene: dict) -> dict:
        preset = PRESETS.get(scene["preset"])
        stages = stages_for(preset) if preset else []
        scene["stages"] = [{"key": s.key, "label": s.label, "description": s.description} for s in stages]
        artifacts_dir = scene_layout(settings, scene["id"]).artifacts
        scene["files"], scene["file_sizes"] = {}, {}
        for key, name in scene["artifacts"].items():
            scene["files"][key] = f"/api/scenes/{scene['id']}/files/{name}"
            path = artifacts_dir / name
            scene["file_sizes"][key] = path.stat().st_size if path.is_file() else None
        scene["preview"] = scene["files"].get("thumbnail")
        if not scene["preview"]:
            thumbs = scene_layout(settings, scene["id"]).thumbs
            names = sorted(p.name for p in thumbs.glob("frame_*.jpg")) if thumbs.is_dir() else []
            if names:
                scene["preview"] = f"/api/scenes/{scene['id']}/frames/{names[len(names) // 2]}"
        return scene

    def get_or_404(scene_id: str) -> dict:
        scene = store.get(scene_id) if _SCENE_ID.match(scene_id) else None
        if scene is None:
            raise HTTPException(404, "Scene not found")
        return scene

    @app.get("/api/health")
    def health() -> dict:
        return {"version": __version__, "checks": run_checks(settings, deep=False)}

    @app.get("/api/system")
    def system() -> dict:
        scenes = store.list()
        usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else REPO_ROOT)
        return {
            "gpu": gpu_stats(),
            "urls": _lan_urls(settings.port),
            "wsl": _is_wsl(),
            "queue": {status: sum(1 for sc in scenes if sc["status"] == status) for status in ("running", "queued")},
            "scenes": len(scenes),
            "disk": {"free": usage.free, "total": usage.total},
        }

    @app.get("/api/pipeline")
    def pipeline() -> list:
        return [{"key": stage.key, "label": stage.label, "description": stage.description,
                 "presets": [p.name for p in PRESETS.values() if stage.applies(p)]} for stage in STAGES]

    diagnostics_cache: dict = {}
    diagnostics_lock = threading.Lock()

    @app.get("/api/diagnostics")
    def diagnostics(refresh: bool = False) -> dict:
        """Full environment check, run in a subprocess so the server itself never loads PyTorch or CUDA."""
        with diagnostics_lock:
            if refresh or not diagnostics_cache:
                out = subprocess.run([settings.python_bin, "-m", "archeon.cli", "doctor", "--json"],
                                     capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT))
                try:
                    diagnostics_cache.update(json.loads(out.stdout.strip().splitlines()[-1]), checked_at=time.time())
                except (ValueError, IndexError):
                    raise HTTPException(500, f"Diagnostics failed: {(out.stderr or out.stdout)[-400:]}")
            return dict(diagnostics_cache)

    @app.get("/api/storage")
    def storage() -> dict:
        rows = []
        for scene in store.list():
            layout = scene_layout(settings, scene["id"])
            video = layout.video
            rows.append({
                "id": scene["id"], "name": scene["name"], "status": scene["status"],
                "video": video.stat().st_size if video else 0,
                "work": _dir_size(layout.work),
                "artifacts": _dir_size(layout.artifacts),
            })
        usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else REPO_ROOT)
        return {"data_dir": str(settings.data_dir), "disk": {"free": usage.free, "total": usage.total},
                "scenes": rows, "total": sum(r["video"] + r["work"] + r["artifacts"] for r in rows)}

    @app.get("/api/presets")
    def presets() -> dict:
        return {"default": DEFAULT_PRESET, "presets": [p.to_dict() for p in PRESETS.values()]}

    @app.get("/api/scenes")
    def list_scenes() -> list:
        return [present(scene) for scene in store.list()]

    @app.post("/api/scenes", status_code=201)
    def create_scene(video: UploadFile = File(...), name: str = Form(""), preset: str = Form(DEFAULT_PRESET)) -> dict:
        if preset not in PRESETS:
            raise HTTPException(400, f"Unknown preset '{preset}'")
        suffix = Path(video.filename or "").suffix.lower() or ".mp4"
        if suffix not in VIDEO_SUFFIXES:
            raise HTTPException(400, f"Unsupported file type '{suffix}'. Upload a video ({', '.join(sorted(VIDEO_SUFFIXES))}).")
        display_name = name.strip() or Path(video.filename or "Untitled capture").stem
        scene = store.create(display_name[:120], preset, source_filename=video.filename, status="uploading")
        layout = scene_layout(settings, scene["id"])
        layout.root.mkdir(parents=True, exist_ok=True)
        limit = settings.max_upload_mb * 1024 * 1024
        written = 0
        try:
            with open(layout.root / f"video{suffix}", "wb") as out:
                while chunk := video.file.read(4 * 1024 * 1024):
                    written += len(chunk)
                    if written > limit:
                        raise HTTPException(413, f"Video is larger than {settings.max_upload_mb} MB")
                    out.write(chunk)
        except BaseException:
            shutil.rmtree(layout.root, ignore_errors=True)
            store.delete(scene["id"])
            raise
        if written == 0:
            shutil.rmtree(layout.root, ignore_errors=True)
            store.delete(scene["id"])
            raise HTTPException(400, "The uploaded file is empty")
        scene = store.update(scene["id"], status="queued")
        worker.notify()
        return present(scene)

    @app.get("/api/scenes/{scene_id}")
    def get_scene(scene_id: str) -> dict:
        return present(get_or_404(scene_id))

    @app.patch("/api/scenes/{scene_id}")
    def rename_scene(scene_id: str, name: str = Form(...)) -> dict:
        get_or_404(scene_id)
        if not name.strip():
            raise HTTPException(400, "Name cannot be empty")
        return present(store.update(scene_id, name=name.strip()[:120]))

    @app.get("/api/scenes/{scene_id}/log")
    def scene_log(scene_id: str, offset: int = 0) -> dict:
        get_or_404(scene_id)
        path = scene_layout(settings, scene_id).log
        if not path.is_file():
            return {"text": "", "offset": 0}
        size = path.stat().st_size
        offset = max(0, min(offset, size))
        if size - offset > 256 * 1024:  # first poll of a long log: only send the tail
            offset = size - 256 * 1024
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
        return {"text": data.decode("utf-8", "replace"), "offset": offset + len(data)}

    @app.post("/api/scenes/{scene_id}/cancel")
    def cancel_scene(scene_id: str) -> dict:
        scene = get_or_404(scene_id)
        if scene["status"] not in ACTIVE_STATUSES:
            raise HTTPException(409, f"Scene is {scene['status']}, nothing to cancel")
        worker.cancel(scene_id)
        return present(store.get(scene_id))

    @app.post("/api/scenes/{scene_id}/retry")
    def retry_scene(scene_id: str) -> dict:
        scene = get_or_404(scene_id)
        if scene["status"] not in RETRYABLE:
            raise HTTPException(409, f"Scene is {scene['status']}; only failed, cancelled or interrupted scenes can be retried")
        if scene_layout(settings, scene_id).video is None:
            raise HTTPException(409, "This scene has no source video to process")
        scene = store.update(scene_id, status="queued", error=None, finished_at=None)
        worker.notify()
        return present(scene)

    @app.post("/api/scenes/{scene_id}/thumbnail")
    def set_thumbnail(scene_id: str, image: UploadFile = File(...)) -> dict:
        """Lets the browser supply a preview for scenes that have none (e.g. imported meshes), captured
        from the 3D viewer. Existing thumbnails are never replaced."""
        scene = get_or_404(scene_id)
        if "thumbnail" in scene["artifacts"]:
            raise HTTPException(409, "Scene already has a thumbnail")
        data = image.file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024 or not data.startswith(b"\xff\xd8"):
            raise HTTPException(400, "Expected a JPEG under 5 MB")
        artifacts_dir = scene_layout(settings, scene_id).artifacts
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "thumbnail.jpg").write_bytes(data)
        return present(store.update(scene_id, artifacts={**scene["artifacts"], "thumbnail": "thumbnail.jpg"}))

    @app.post("/api/scenes/{scene_id}/clean")
    def clean_scene(scene_id: str) -> dict:
        """Delete a finished scene's intermediate files (checkpoints, COLMAP data, full-size frames).
        Frame thumbnails and the camera reconstruction are kept for the UI."""
        scene = get_or_404(scene_id)
        if scene["status"] != "done":
            raise HTTPException(409, "Only finished scenes can be cleaned up")
        work = scene_layout(settings, scene_id).work
        before = _dir_size(work)
        if work.is_dir():
            keep = {"thumbs", "reconstruction.json"}
            for item in work.iterdir():
                if item.name in keep:
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
        return {"freed": before - _dir_size(work)}

    @app.delete("/api/scenes/{scene_id}", status_code=204, response_class=Response)
    def delete_scene(scene_id: str) -> Response:
        get_or_404(scene_id)
        worker.delete(scene_id)
        return Response(status_code=204)

    @app.get("/api/scenes/{scene_id}/frames")
    def scene_frames(scene_id: str) -> dict:
        get_or_404(scene_id)
        thumbs = scene_layout(settings, scene_id).thumbs
        names = sorted(p.name for p in thumbs.glob("frame_*.jpg")) if thumbs.is_dir() else []
        return {"frames": [{"name": n, "thumb": f"/api/scenes/{scene_id}/frames/{n}",
                            "full": f"/api/scenes/{scene_id}/frames/{n}?full=1"} for n in names]}

    @app.get("/api/scenes/{scene_id}/frames/{name}")
    def scene_frame(scene_id: str, name: str, full: bool = False) -> FileResponse:
        get_or_404(scene_id)
        layout = scene_layout(settings, scene_id)
        path = (layout.frames if full else layout.thumbs) / name
        if not _FRAME_NAME.match(name) or not path.is_file():
            raise HTTPException(404, "Frame not found")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/scenes/{scene_id}/reconstruction")
    def scene_reconstruction(scene_id: str) -> FileResponse:
        get_or_404(scene_id)
        path = scene_layout(settings, scene_id).work / "reconstruction.json"
        if not path.is_file():
            raise HTTPException(404, "No camera reconstruction yet")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/scenes/{scene_id}/files/{name}")
    def scene_file(scene_id: str, name: str) -> FileResponse:
        scene = get_or_404(scene_id)
        if name not in scene["artifacts"].values():
            raise HTTPException(404, "File not found")
        path = scene_layout(settings, scene_id).artifacts / name
        if not path.is_file():
            raise HTTPException(404, "File not found")
        media_type = "application/octet-stream" if path.suffix in {".ply", ".splat", ".obj", ".mtl"} else None
        download = f"{_slug(scene['name'])}-{name}"
        return FileResponse(path, media_type=media_type, filename=download,
                            content_disposition_type="inline" if path.suffix in {".jpg", ".png", ".json"} else "attachment")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _lan_urls(port: int) -> list[str]:
    """Addresses other devices on the network can try (e.g. a phone recording a capture)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))  # TEST-NET address: no packet is sent, this only picks a route
            return [f"http://{sock.getsockname()[0]}:{port}"]
    except OSError:
        return []


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower() or "scene"
