"""The processing pipeline: video -> frames -> COLMAP -> 3DGS -> SuGaR -> exported artifacts."""

from __future__ import annotations

from ..presets import Preset
from . import colmap, export, frames, gaussians, sugar
from .base import Cancelled, SceneLayout, Stage, StageContext, StageError

_needs_sugar = lambda preset: preset.sugar  # noqa: E731

# Weights roughly track wall-clock time on an RTX 4060 so the overall progress bar moves evenly.
STAGES: list[Stage] = [
    Stage("frames", "Extracting frames", 2, frames.run, description=(
        "Decoding the video and keeping the sharpest frame from each moment, so motion blur "
        "does not confuse the reconstruction.")),
    Stage("colmap", "Estimating camera poses", 10, colmap.run, description=(
        "COLMAP matches features between frames to work out where the camera was for each one, "
        "and triangulates a sparse 3D point cloud.")),
    Stage("gaussians", "Training Gaussian splats", 20, gaussians.run, description=(
        "Optimising hundreds of thousands of 3D Gaussians until their renders match every frame. "
        "This is the photoreal splat you can fly through.")),
    Stage("sugar_coarse", "Aligning splats to surfaces", 40, sugar.run_coarse, _needs_sugar, description=(
        "SuGaR regularises the Gaussians to flatten onto the scene's surfaces, so that a clean mesh "
        "can be extracted from them.")),
    Stage("sugar_mesh", "Extracting mesh", 8, sugar.run_mesh, _needs_sugar, description=(
        "Sampling the aligned Gaussians' density level set and running Poisson reconstruction to "
        "build a triangle mesh.")),
    Stage("sugar_refine", "Refining mesh-bound splats", 12, sugar.run_refine, _needs_sugar, description=(
        "Binding new Gaussians to the mesh triangles and optimising mesh and splats together.")),
    Stage("sugar_texture", "Texturing mesh", 6, sugar.run_texture, _needs_sugar, description=(
        "Baking a UV texture for the mesh from the refined Gaussians.")),
    Stage("export", "Packaging results", 2, export.run, description=(
        "Writing the .ply, .splat, .obj and .glb files, a thumbnail and a manifest.")),
]


def stages_for(preset: Preset) -> list[Stage]:
    return [stage for stage in STAGES if stage.applies(preset)]


__all__ = ["STAGES", "Cancelled", "SceneLayout", "Stage", "StageContext", "StageError", "stages_for"]
