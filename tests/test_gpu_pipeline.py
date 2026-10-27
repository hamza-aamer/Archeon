"""End-to-end run on the bundled sample capture. Needs the full setup (GPU, COLMAP, CUDA extensions).

    pytest -m gpu

The sample is a real 2.4 s phone clip that mostly rotates in place, which is a hard case for COLMAP: its
initial-pair search is not deterministic, and on some runs it cannot register enough frames. A failure here
with "COLMAP only placed N of M frames" is the capture, not the pipeline.
"""

import dataclasses
import shutil
import subprocess

import pytest

from archeon.config import REPO_ROOT, get_settings
from archeon.db import SceneStore
from archeon.pipeline.splat_format import read_splat
from archeon.worker import run_scene, scene_layout

pytestmark = pytest.mark.gpu

SAMPLE = REPO_ROOT / "samples" / "capture.mp4"


def _gpu_available() -> bool:
    return shutil.which("nvidia-smi") is not None and subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _gpu_available(), reason="no NVIDIA GPU")
def test_preview_pipeline_on_sample(tmp_path):
    settings = dataclasses.replace(get_settings(), data_dir=tmp_path / "data")
    store = SceneStore(settings.db_path)
    scene = store.create("sample", "preview")
    layout = scene_layout(settings, scene["id"])
    layout.root.mkdir(parents=True)
    shutil.copyfile(SAMPLE, layout.root / "video.mp4")

    status = run_scene(store, settings, scene["id"])
    final = store.get(scene["id"])
    assert status == "done", final["error"]
    assert final["stats"]["registered_images"] >= 0.5 * final["stats"]["frames_selected"]
    for name in ("scene.ply", "scene.splat", "thumbnail.jpg", "manifest.json"):
        assert (layout.artifacts / name).is_file(), name
    assert len(read_splat(layout.artifacts / "scene.splat")) > 1000
    assert set(final["stats"]["view"]) == {"position", "look_at", "up"}
