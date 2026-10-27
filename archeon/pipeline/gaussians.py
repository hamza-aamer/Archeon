"""Stage 3: optimise a 3D Gaussian Splatting model (the vanilla 3DGS trainer bundled with SuGaR)."""

from __future__ import annotations

import socket
from pathlib import Path

from .base import StageContext, StageError, fraction_parser


def ply_path(ctx: StageContext) -> Path:
    return ctx.layout.gs_model / "point_cloud" / f"iteration_{ctx.preset.gs_iterations}" / "point_cloud.ply"


def count_gaussians(path: Path) -> int:
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace").strip()
            if line.startswith("element vertex"):
                return int(line.split()[-1])
            if line == "end_header":
                break
    return 0


def _free_port() -> int:
    # 3DGS always opens a viewer socket; give it a free one so it never collides with anything.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(ctx: StageContext) -> None:
    iterations = str(ctx.preset.gs_iterations)
    trainer = ctx.settings.sugar_dir / "gaussian_splatting" / "train.py"
    if not trainer.is_file():
        raise StageError(f"SuGaR is missing at {ctx.settings.sugar_dir}. Run `git submodule update --init`.")
    ctx.run(
        [ctx.settings.python_bin, trainer,
         "-s", ctx.layout.dataset, "-m", ctx.layout.gs_model,
         "--iterations", iterations, "--save_iterations", iterations, "--test_iterations", iterations,
         "--port", str(_free_port())],
        cwd=ctx.layout.work,
        parser=fraction_parser(r"Training progress:\s*(\d+)%", total=100),
    )
    output = ply_path(ctx)
    if not output.is_file():
        raise StageError("3DGS training finished without writing a point cloud.")
    ctx.stats["gaussians_3dgs"] = count_gaussians(output)
