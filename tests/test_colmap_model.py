import struct

import numpy as np

from archeon.pipeline.colmap_model import (
    count_points, count_registered_images, initial_view, read_camera_poses, read_points,
)


def write_model(model_dir, cameras, points):
    """cameras: list of (name, qvec wxyz, tvec); points: list of xyz."""
    model_dir.mkdir(parents=True, exist_ok=True)
    with open(model_dir / "images.bin", "wb") as fh:
        fh.write(struct.pack("<Q", len(cameras)))
        for image_id, (name, q, t) in enumerate(cameras, start=1):
            fh.write(struct.pack("<i7di", image_id, *q, *t, 1))
            fh.write(name.encode() + b"\x00")
            fh.write(struct.pack("<Q", 2))
            fh.write(struct.pack("<ddq", 1.0, 2.0, -1) * 2)
    with open(model_dir / "points3D.bin", "wb") as fh:
        fh.write(struct.pack("<Q", len(points)))
        for point_id, xyz in enumerate(points, start=1):
            fh.write(struct.pack("<Q3d3BdQ", point_id, *xyz, 10, 20, 30, 0.5, 2))
            fh.write(struct.pack("<ii", 1, 0) * 2)


def test_reads_poses_points_and_view(tmp_path):
    model = tmp_path / "sparse" / "0"
    identity = (1.0, 0.0, 0.0, 0.0)
    write_model(model, [("b.jpg", identity, (0.0, 0.0, 5.0)), ("a.jpg", identity, (1.0, 0.0, 5.0))],
                [(0, 0, 0), (1, 1, 1), (2, 2, 2)])

    assert count_registered_images(model) == 2
    assert count_points(model) == 3
    poses = read_camera_poses(model)
    assert [p[0] for p in poses] == ["b.jpg", "a.jpg"]
    np.testing.assert_allclose(poses[0][2], [0, 0, -5])  # center = -R^T t
    np.testing.assert_allclose(read_points(model)[1], [1, 1, 1])

    view = initial_view(model)
    assert view["position"] == [-1.0, 0.0, -5.0]  # first image by name ("a.jpg")
    assert view["look_at"] == [1.0, 1.0, 1.0]
    assert view["up"] == [0.0, -1.0, 0.0]  # COLMAP cameras have +y down


def test_missing_model_counts_zero(tmp_path):
    assert count_registered_images(tmp_path) == 0
    assert count_points(tmp_path) == 0
