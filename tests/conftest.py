from __future__ import annotations

import sys
from pathlib import Path

import pytest

from archeon.config import Settings
from archeon.db import SceneStore


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        sugar_dir=tmp_path / "sugar",
        colmap_bin=None,
        ffmpeg_bin=None,
        ffprobe_bin=None,
        python_bin=sys.executable,
        host="127.0.0.1",
        port=0,
        max_upload_mb=1,
    )


@pytest.fixture
def store(settings: Settings) -> SceneStore:
    return SceneStore(settings.db_path)
