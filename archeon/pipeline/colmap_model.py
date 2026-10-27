"""Minimal readers for COLMAP's binary sparse model (images.bin / points3D.bin)."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


def count_registered_images(model_dir: Path) -> int:
    path = model_dir / "images.bin"
    if not path.is_file():
        return 0
    with open(path, "rb") as fh:
        return struct.unpack("<Q", fh.read(8))[0]


def count_points(model_dir: Path) -> int:
    path = model_dir / "points3D.bin"
    if not path.is_file():
        return 0
    with open(path, "rb") as fh:
        return struct.unpack("<Q", fh.read(8))[0]


def read_camera_poses(model_dir: Path) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """Return (image name, world-from-camera rotation, camera center) for each registered image."""
    poses = []
    with open(model_dir / "images.bin", "rb") as fh:
        (count,) = struct.unpack("<Q", fh.read(8))
        for _ in range(count):
            _image_id, qw, qx, qy, qz, tx, ty, tz, _camera_id = struct.unpack("<i7di", fh.read(64))
            name = bytearray()
            while (char := fh.read(1)) != b"\x00":
                name += char
            (n_points2d,) = struct.unpack("<Q", fh.read(8))
            fh.seek(24 * n_points2d, 1)
            rotation = _quat_to_matrix(qw, qx, qy, qz)  # camera-from-world
            center = -rotation.T @ np.array([tx, ty, tz])
            poses.append((name.decode(), rotation.T, center))
    return poses


def read_colored_points(model_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (N x 3 float64 positions, N x 3 uint8 colours)."""
    points, colors = [], []
    with open(model_dir / "points3D.bin", "rb") as fh:
        (count,) = struct.unpack("<Q", fh.read(8))
        for _ in range(count):
            _pid, x, y, z, r, g, b, _err, track_length = struct.unpack("<Q3d3BdQ", fh.read(51))
            fh.seek(8 * track_length, 1)
            points.append((x, y, z))
            colors.append((r, g, b))
    return (np.asarray(points, dtype=np.float64).reshape(-1, 3),
            np.asarray(colors, dtype=np.uint8).reshape(-1, 3))


def read_points(model_dir: Path) -> np.ndarray:
    return read_colored_points(model_dir)[0]


def reconstruction_summary(model_dir: Path, max_points: int = 40_000) -> dict:
    """Sparse points (subsampled) and camera poses, for drawing the capture path in the browser."""
    xyz, rgb = read_colored_points(model_dir)
    if len(xyz) > max_points:
        keep = np.random.default_rng(0).choice(len(xyz), max_points, replace=False)
        xyz, rgb = xyz[keep], rgb[keep]
    cameras = []
    for name, world_from_cam, center in sorted(read_camera_poses(model_dir), key=lambda pose: pose[0]):
        cameras.append({
            "name": name,
            "center": center.round(4).tolist(),
            "forward": (world_from_cam @ [0.0, 0.0, 1.0]).round(4).tolist(),
            "up": (-(world_from_cam @ [0.0, 1.0, 0.0])).round(4).tolist(),
        })
    return {
        "points": xyz.round(4).ravel().tolist(),
        "colors": rgb.ravel().tolist(),
        "cameras": cameras,
        "view": initial_view(model_dir),
    }


def initial_view(model_dir: Path) -> dict:
    """A sensible starting camera for the web viewer: from the first capture pose, looking at the scene,
    with 'up' taken from the average camera orientation (COLMAP cameras look down +z with +y pointing down)."""
    poses = sorted(read_camera_poses(model_dir), key=lambda pose: pose[0])
    points = read_points(model_dir)
    world_from_cams = np.stack([pose[1] for pose in poses])
    centers = np.stack([pose[2] for pose in poses])

    up = -(world_from_cams @ np.array([0.0, 1.0, 0.0])).mean(axis=0)
    up /= np.linalg.norm(up) or 1.0
    look_at = np.median(points, axis=0) if len(points) else centers.mean(axis=0)
    return {
        "position": centers[0].round(4).tolist(),
        "look_at": look_at.round(4).tolist(),
        "up": up.round(4).tolist(),
    }


def _quat_to_matrix(w: float, x: float, y: float, z: float) -> np.ndarray:
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])
