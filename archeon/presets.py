"""Quality presets.

These follow the upstream defaults (3DGS's 1600 px resolution cap, SuGaR's 15k refinement iterations) rather
than being shrunk to fit small GPUs. VRAM figures are guidance: the 3DGS authors specify 24 GB for
paper-quality training, and SuGaR adds its own models on top while keeping every training image on the GPU.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    description: str
    max_frames: int
    max_side: int
    gs_iterations: int
    sugar: bool
    min_vram_gb: int
    recommended_vram_gb: int
    estimate: str  # rough wall-clock estimate on a recommended GPU
    # SuGaR options (ignored when sugar=False)
    n_vertices: int = 200_000
    gaussians_per_triangle: int = 6
    refinement_iterations: int = 15_000

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        Preset(
            name="preview",
            label="Preview",
            description="Gaussian splat only (3DGS, 7k iterations). The quick way to check a capture.",
            max_frames=150,
            max_side=1600,
            gs_iterations=7_000,
            sugar=False,
            min_vram_gb=8,
            recommended_vram_gb=12,
            estimate="10–20 min",
        ),
        Preset(
            name="standard",
            label="Standard",
            description="Splat + SuGaR textured mesh: 200k-vertex mesh, 6 Gaussians per triangle, full refinement.",
            max_frames=200,
            max_side=1600,
            gs_iterations=7_000,
            sugar=True,
            min_vram_gb=16,
            recommended_vram_gb=24,
            estimate="1–1.5 h",
            n_vertices=200_000,
            gaussians_per_triangle=6,
            refinement_iterations=15_000,
        ),
        Preset(
            name="high",
            label="High",
            description="Splat + high-poly SuGaR mesh: 1M vertices, full refinement. Best detail for large scenes.",
            max_frames=300,
            max_side=1600,
            gs_iterations=7_000,
            sugar=True,
            min_vram_gb=24,
            recommended_vram_gb=32,
            estimate="1.5–3 h",
            n_vertices=1_000_000,
            gaussians_per_triangle=1,
            refinement_iterations=15_000,
        ),
    )
}

DEFAULT_PRESET = "standard"
