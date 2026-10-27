"""Convert a 3DGS .ply into the compact `.splat` format (32 bytes per Gaussian) that web viewers load quickly.

Layout per Gaussian (little endian): position float32x3, scale float32x3 (linear), RGBA uint8x4,
rotation uint8x4 (w, x, y, z quaternion mapped from [-1, 1] to [0, 255]). Only the base colour (SH DC
term) is kept. Gaussians are sorted largest/most opaque first so progressive loading looks good.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from plyfile import PlyData

SH_C0 = 0.28209479177387814

SPLAT_DTYPE = np.dtype([("position", "<f4", 3), ("scale", "<f4", 3), ("rgba", "u1", 4), ("rotation", "u1", 4)])


def ply_to_splat(ply_path: Path, splat_path: Path, min_opacity: float = 1.0 / 255.0) -> int:
    vertex = PlyData.read(str(ply_path))["vertex"]

    def stack(*names: str) -> np.ndarray:
        return np.stack([np.asarray(vertex[name], dtype=np.float32) for name in names], axis=1)

    position = stack("x", "y", "z")
    scale = np.exp(stack("scale_0", "scale_1", "scale_2"))
    rotation = stack("rot_0", "rot_1", "rot_2", "rot_3")
    rotation /= np.linalg.norm(rotation, axis=1, keepdims=True).clip(min=1e-12)
    opacity = 1.0 / (1.0 + np.exp(-np.asarray(vertex["opacity"], dtype=np.float32)))
    color = 0.5 + SH_C0 * stack("f_dc_0", "f_dc_1", "f_dc_2")

    keep = (opacity >= min_opacity) & np.isfinite(position).all(axis=1) & np.isfinite(scale).all(axis=1)
    order = np.argsort(-(scale.prod(axis=1) * opacity)[keep], kind="stable")
    index = np.flatnonzero(keep)[order]

    out = np.empty(len(index), dtype=SPLAT_DTYPE)
    out["position"] = position[index]
    out["scale"] = scale[index]
    out["rgba"][:, :3] = (color[index].clip(0, 1) * 255).round()
    out["rgba"][:, 3] = (opacity[index] * 255).round()
    out["rotation"] = (rotation[index] * 128 + 128).round().clip(0, 255)
    splat_path.parent.mkdir(parents=True, exist_ok=True)
    out.tofile(str(splat_path))
    return len(out)


def read_splat(path: Path) -> np.ndarray:
    return np.fromfile(str(path), dtype=SPLAT_DTYPE)
