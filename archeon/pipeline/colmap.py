"""Stage 2: recover camera poses with COLMAP and write an undistorted dataset for 3DGS / SuGaR."""

from __future__ import annotations

import json
import shutil

from .base import StageContext, StageError, fraction_parser
from .colmap_model import count_points, count_registered_images, reconstruction_summary

MIN_REGISTERED_RATIO = 0.5


def run(ctx: StageContext) -> None:
    colmap = ctx.settings.colmap_bin
    if not colmap:
        raise StageError("COLMAP not found. Run scripts/setup.sh or set ARCHEON_COLMAP.")
    layout = ctx.layout
    frames = sorted(layout.frames.glob("*.jpg"))
    n_frames = len(frames)

    shutil.rmtree(layout.colmap, ignore_errors=True)
    shutil.rmtree(layout.dataset, ignore_errors=True)
    sparse = layout.colmap / "sparse"
    sparse.mkdir(parents=True)
    database = layout.colmap / "database.db"
    env = {"QT_QPA_PLATFORM": "offscreen"}

    ctx.run(
        [colmap, "feature_extractor",
         "--database_path", database, "--image_path", layout.frames,
         "--ImageReader.single_camera", "1", "--ImageReader.camera_model", "SIMPLE_RADIAL",
         "--FeatureExtraction.use_gpu", "1"],
        env=env, parser=fraction_parser(r"Processed file \[(\d+)/(\d+)\]"), segment=(0.0, 0.2),
    )
    # Frames come from a continuous walk, so sequential matching (with quadratic overlap to bridge
    # gaps) is much faster than exhaustive matching and just as reliable.
    ctx.run(
        [colmap, "sequential_matcher", "--database_path", database,
         "--SequentialMatching.overlap", "15", "--SequentialMatching.quadratic_overlap", "1",
         "--FeatureMatching.use_gpu", "1"],
        env=env, parser=fraction_parser(r"(?:Processing|Matching) image \[(\d+)/(\d+)\]"), segment=(0.2, 0.4),
    )
    ctx.run(
        [colmap, "mapper", "--database_path", database, "--image_path", layout.frames, "--output_path", sparse],
        env=env, segment=(0.4, 0.92),
        parser=fraction_parser(r"Registering image #\d+ \((?:num_reg_frames=)?(\d+)\)", total=n_frames),
    )

    models = [d for d in sparse.iterdir() if d.is_dir()]
    if not models:
        raise StageError("COLMAP could not reconstruct the scene. Record slower, with more overlap and texture.")
    best = max(models, key=count_registered_images)
    registered = count_registered_images(best)
    ctx.log(f"COLMAP built {len(models)} model(s); using {best.name} with {registered}/{n_frames} images")
    if registered < MIN_REGISTERED_RATIO * n_frames:
        raise StageError(
            f"COLMAP only placed {registered} of {n_frames} frames. Record slower, keep the subject in view, "
            "and avoid blank walls, glare and moving objects."
        )

    ctx.run(
        [colmap, "image_undistorter", "--image_path", layout.frames, "--input_path", best,
         "--output_path", layout.dataset, "--output_type", "COLMAP"],
        env=env, segment=(0.92, 1.0),
    )
    # 3DGS expects the model under sparse/0.
    model_dir = layout.dataset / "sparse" / "0"
    model_dir.mkdir(parents=True, exist_ok=True)
    for item in (layout.dataset / "sparse").iterdir():
        if item.is_file():
            shutil.move(str(item), model_dir / item.name)
    for leftover in ("stereo", "run-colmap-geometric.sh", "run-colmap-photometric.sh"):
        path = layout.dataset / leftover
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    ctx.stats.update(registered_images=registered, sparse_points=count_points(model_dir))
    (layout.work / "reconstruction.json").write_text(json.dumps(reconstruction_summary(model_dir)))
