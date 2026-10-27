"""Final stage: collect results into artifacts/ with stable names, plus web-friendly derivatives."""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

import numpy as np

from . import gaussians
from .base import StageContext, StageError
from .colmap_model import initial_view
from .frames import write_thumbnail
from .splat_format import ply_to_splat


def run(ctx: StageContext) -> None:
    layout = ctx.layout
    shutil.rmtree(layout.artifacts, ignore_errors=True)
    layout.artifacts.mkdir(parents=True)

    vanilla = gaussians.ply_path(ctx)
    if not vanilla.is_file():
        raise StageError("No trained Gaussian splat found to export.")
    add_splat(ctx, vanilla, "scene")
    ctx.progress(0.3)

    if ctx.preset.sugar:
        state = json.loads(layout.sugar_state.read_text())
        refined_ply = next(iter(sorted((layout.work / "output" / "refined_ply" / layout.dataset.name).glob("*.ply"))),
                           None)
        if refined_ply:
            add_splat(ctx, refined_ply, "sugar")
        ctx.progress(0.5)
        add_mesh(ctx, Path(state["refined_mesh"]))
    ctx.progress(0.9)

    frames = sorted(layout.frames.glob("*.jpg"))
    if frames:
        write_thumbnail(frames[len(frames) // 2], layout.artifacts / "thumbnail.jpg", long_side=960, quality=85)
        ctx.artifacts["thumbnail"] = "thumbnail.jpg"
    ctx.stats["view"] = initial_view(layout.dataset / "sparse" / "0")
    write_manifest(ctx)


def add_splat(ctx: StageContext, ply: Path, prefix: str) -> None:
    artifacts = ctx.layout.artifacts
    shutil.copyfile(ply, artifacts / f"{prefix}.ply")
    count = ply_to_splat(ply, artifacts / f"{prefix}.splat")
    ctx.artifacts[f"{prefix}_ply"] = f"{prefix}.ply"
    ctx.artifacts[f"{prefix}_splat"] = f"{prefix}.splat"
    ctx.stats[f"{prefix}_splat_count"] = count


def add_mesh(ctx: StageContext, obj: Path) -> None:
    """Copy SuGaR's textured OBJ under stable names, then derive a GLB for the browser and a zip for download."""
    artifacts = ctx.layout.artifacts
    mtl, texture = obj.with_suffix(".mtl"), obj.with_suffix(".png")
    _copy_obj(obj, artifacts / "mesh.obj")
    if mtl.is_file():
        lines = ["map_Kd mesh.png" if line.strip().startswith("map_Kd") else line
                 for line in mtl.read_text().splitlines()]
        (artifacts / "mesh.mtl").write_text("\n".join(lines) + "\n")
    if texture.is_file():
        shutil.copyfile(texture, artifacts / "mesh.png")
    ctx.artifacts["mesh_obj"] = "mesh.obj"

    with zipfile.ZipFile(artifacts / "mesh.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
        for name in ("mesh.obj", "mesh.mtl", "mesh.png"):
            if (artifacts / name).is_file():
                bundle.write(artifacts / name, name)
    ctx.artifacts["mesh_zip"] = "mesh.zip"

    try:
        import trimesh

        mesh = trimesh.load(str(artifacts / "mesh.obj"), force="mesh", process=False)
        mesh.export(str(artifacts / "mesh.glb"))
        ctx.artifacts["mesh_glb"] = "mesh.glb"
        # The GLB duplicates vertices along UV seams; report the mesh's real (unique) vertex count.
        unique_vertices = len(np.unique(np.asarray(mesh.vertices), axis=0))
        ctx.stats.update(mesh_vertices=int(unique_vertices), mesh_faces=int(len(mesh.faces)))
    except Exception as exc:  # the OBJ is still downloadable, only the in-browser preview is lost
        ctx.log(f"warning: could not convert the mesh to GLB for the web viewer: {exc}")


def _copy_obj(src: Path, dst: Path) -> None:
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        for raw in fin:
            if raw.startswith(b"mtllib "):
                fout.write(b"mtllib mesh.mtl\n")
                continue
            fout.write(raw)
            if raw.startswith(b"v "):  # past the header: copy the remainder in bulk
                shutil.copyfileobj(fin, fout, 16 * 1024 * 1024)
                break


def write_manifest(ctx: StageContext) -> None:
    ctx.artifacts["manifest"] = "manifest.json"
    manifest = {
        "preset": ctx.preset.name,
        "exported_at": time.time(),
        "stats": ctx.stats,
        "artifacts": ctx.artifacts,
    }
    (ctx.layout.artifacts / "manifest.json").write_text(json.dumps(manifest, indent=2))
