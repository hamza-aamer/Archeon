"""Command line entry point: `archeon serve | process | import | doctor`."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from pathlib import Path

from .config import get_settings
from .db import SceneStore
from .presets import DEFAULT_PRESET, PRESETS


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    settings = get_settings()
    host, port = args.host or settings.host, args.port or settings.port
    print(f"Archeon UI: http://localhost:{port}  (data in {settings.data_dir})")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    from .worker import run_scene, scene_layout

    settings = get_settings()
    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        print(f"error: {video} does not exist", file=sys.stderr)
        return 2
    store = SceneStore(settings.db_path)
    scene = store.create(args.name or video.stem, args.preset, source_filename=video.name)
    layout = scene_layout(settings, scene["id"])
    layout.root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, layout.root / f"video{video.suffix.lower() or '.mp4'}")
    print(f"scene {scene['id']} ({args.preset}); log: {layout.log}")

    cancel = threading.Event()
    result: dict = {}
    runner = threading.Thread(target=lambda: result.update(status=run_scene(store, settings, scene["id"], cancel)))
    runner.start()
    offset = 0
    try:
        while runner.is_alive():
            runner.join(timeout=0.5)
            offset = _echo_log(layout.log, offset)
    except KeyboardInterrupt:
        print("\ncancelling...")
        cancel.set()
        runner.join()
    _echo_log(layout.log, offset)

    final = store.get(scene["id"])
    print(f"\nstatus: {final['status']}" + (f" - {final['error']}" if final["error"] else ""))
    if final["status"] == "done":
        print(f"artifacts: {layout.artifacts}")
        print(json.dumps(final["stage_times"], indent=2))
    return 0 if final["status"] == "done" else 1


def _echo_log(path: Path, offset: int) -> int:
    if not path.is_file():
        return offset
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    if data:
        sys.stdout.write(data.decode("utf-8", "replace"))
        sys.stdout.flush()
    return offset + len(data)


def cmd_import(args: argparse.Namespace) -> int:
    """Register existing results (a 3DGS/SuGaR .ply and/or a SuGaR textured .obj) as a finished scene."""
    from .pipeline import SceneLayout, StageContext
    from .pipeline.export import add_mesh, add_splat, write_manifest

    if not args.ply and not args.obj:
        print("error: pass --ply and/or --obj", file=sys.stderr)
        return 2
    settings = get_settings()
    store = SceneStore(settings.db_path)
    scene = store.create(args.name, "imported", status="running")
    layout = SceneLayout(settings.scenes_dir / scene["id"])
    layout.artifacts.mkdir(parents=True, exist_ok=True)
    ctx = StageContext(settings, layout, PRESETS["preview"])
    try:
        if args.ply:
            add_splat(ctx, Path(args.ply).expanduser().resolve(), "scene")
        if args.obj:
            add_mesh(ctx, Path(args.obj).expanduser().resolve())
        if args.thumbnail:
            shutil.copyfile(args.thumbnail, layout.artifacts / "thumbnail.jpg")
            ctx.artifacts["thumbnail"] = "thumbnail.jpg"
        write_manifest(ctx)
    except Exception as exc:
        store.update(scene["id"], status="failed", error=str(exc), finished_at=time.time())
        raise
    store.update(scene["id"], status="done", progress=1.0, finished_at=time.time(),
                 artifacts=ctx.artifacts, stats=ctx.stats)
    print(f"imported as scene {scene['id']}: {', '.join(ctx.artifacts.values())}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_checks, versions

    checks = run_checks(get_settings(), deep=True)
    if args.json:
        print(json.dumps({"checks": checks, "versions": versions(get_settings())}))
        return 0
    for check in checks:
        mark = "ok  " if check["ok"] else "FAIL"
        print(f"[{mark}] {check['name']}" + (f": {check['detail']}" if check["detail"] else ""))
    failed = [c for c in checks if not c["ok"]]
    print("\nAll checks passed." if not failed else f"\n{len(failed)} check(s) failed.")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archeon", description="Video -> Gaussian splats + SuGaR mesh")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web UI and processing worker")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=cmd_serve)

    process = sub.add_parser("process", help="process one video without the web UI")
    process.add_argument("video")
    process.add_argument("--preset", choices=sorted(PRESETS), default=DEFAULT_PRESET)
    process.add_argument("--name")
    process.set_defaults(func=cmd_process)

    imp = sub.add_parser("import", help="add existing .ply / SuGaR .obj results to the library")
    imp.add_argument("--name", required=True)
    imp.add_argument("--ply", help="3DGS-format Gaussian splat .ply")
    imp.add_argument("--obj", help="textured .obj (with .mtl/.png next to it)")
    imp.add_argument("--thumbnail", help="optional .jpg preview image")
    imp.set_defaults(func=cmd_import)

    doctor = sub.add_parser("doctor", help="check GPU, CUDA extensions, COLMAP and ffmpeg")
    doctor.add_argument("--json", action="store_true", help="machine-readable output (used by the web UI)")
    doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
