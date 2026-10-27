import numpy as np
from plyfile import PlyData, PlyElement

from archeon.pipeline.splat_format import SH_C0, ply_to_splat, read_splat


def write_gaussians(path, positions, log_scales, quats, opacity_logits, dc):
    names = (["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
             + [f"f_rest_{i}" for i in range(45)]
             + ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"])
    data = np.zeros(len(positions), dtype=[(n, "f4") for n in names])
    for i, axis in enumerate("xyz"):
        data[axis] = positions[:, i]
        data[f"scale_{i}"] = log_scales[:, i]
        data[f"f_dc_{i}"] = dc[:, i]
    for i in range(4):
        data[f"rot_{i}"] = quats[:, i]
    data["opacity"] = opacity_logits
    PlyData([PlyElement.describe(data, "vertex")]).write(str(path))


def test_ply_to_splat_converts_and_orders(tmp_path):
    positions = np.array([[0, 0, 0], [1, 2, 3], [4, 5, 6]], dtype=np.float32)
    log_scales = np.log(np.array([[0.1, 0.1, 0.1], [0.5, 0.5, 0.5], [0.2, 0.2, 0.2]], dtype=np.float32))
    quats = np.array([[2, 0, 0, 0], [0, 1, 0, 0], [1, 1, 0, 0]], dtype=np.float32)  # unnormalised on purpose
    opacity_logits = np.array([5.0, 5.0, -20.0], dtype=np.float32)  # last one is ~transparent -> pruned
    dc = np.array([[0, 0, 0], [1 / SH_C0 * 0.5, -1 / SH_C0 * 0.5, 0], [0, 0, 0]], dtype=np.float32)
    ply = tmp_path / "in.ply"
    write_gaussians(ply, positions, log_scales, quats, opacity_logits, dc)

    count = ply_to_splat(ply, tmp_path / "out.splat")
    splats = read_splat(tmp_path / "out.splat")

    assert count == 2 and len(splats) == 2
    assert (tmp_path / "out.splat").stat().st_size == 2 * 32
    # Largest Gaussian first.
    np.testing.assert_allclose(splats["position"][0], [1, 2, 3])
    np.testing.assert_allclose(splats["scale"][0], [0.5, 0.5, 0.5], rtol=1e-5)
    np.testing.assert_array_equal(splats["rgba"][0][:3], [255, 0, 128])
    assert splats["rgba"][0][3] == round(255 / (1 + np.exp(-5.0)))
    np.testing.assert_array_equal(splats["rotation"][0], [128, 255, 128, 128])
    np.testing.assert_array_equal(splats["rotation"][1], [255, 128, 128, 128])
