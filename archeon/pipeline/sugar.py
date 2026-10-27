"""Stages 4-7: SuGaR surface alignment, mesh extraction, refinement and texturing."""

from __future__ import annotations

import json
import os

from ..config import REPO_ROOT
from .base import StageContext, StageError, fraction_parser

_ITERATION = r"\[\s*(\d+)/\s*(\d+)\]"  # SuGaR logs "loss: ...  [ 1200/15000]"


def _run_step(ctx: StageContext, step: str, parser=None) -> None:
    sugar_dir = ctx.settings.sugar_dir
    if not (sugar_dir / "sugar_trainers").is_dir():
        raise StageError(f"SuGaR is missing at {sugar_dir}. Run `git submodule update --init`.")
    preset = ctx.preset
    pythonpath = os.pathsep.join(
        str(p) for p in (sugar_dir, sugar_dir / "gaussian_splatting", REPO_ROOT)
    )
    ctx.run(
        [ctx.settings.python_bin, "-m", "archeon.pipeline.sugar_step", step,
         "--scene", ctx.layout.dataset, "--checkpoint", ctx.layout.gs_model,
         "--iteration", str(preset.gs_iterations), "--state", ctx.layout.sugar_state,
         "--n-vertices", str(preset.n_vertices),
         "--gaussians-per-triangle", str(preset.gaussians_per_triangle),
         "--refinement-iterations", str(preset.refinement_iterations)],
        cwd=ctx.layout.work, env={"PYTHONPATH": pythonpath}, parser=parser,
    )
    state = json.loads(ctx.layout.sugar_state.read_text()) if ctx.layout.sugar_state.is_file() else {}
    key = {"coarse": "coarse", "mesh": "coarse_mesh", "refine": "refined", "texture": "refined_mesh"}[step]
    if not state.get(key):
        raise StageError(f"SuGaR {step} step finished without reporting its output.")


def run_coarse(ctx: StageContext) -> None:
    _run_step(ctx, "coarse", fraction_parser(_ITERATION))


def run_mesh(ctx: StageContext) -> None:
    _run_step(ctx, "mesh")


def run_refine(ctx: StageContext) -> None:
    _run_step(ctx, "refine", fraction_parser(_ITERATION))


def run_texture(ctx: StageContext) -> None:
    _run_step(ctx, "texture")
