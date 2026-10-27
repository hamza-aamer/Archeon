"""Runtime settings, read from environment variables and an optional `.env` at the repo root."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _find_tool(name: str, explicit: str | None) -> str | None:
    """Resolve an external binary: explicit setting, then PATH, then the sibling `archeon-tools` conda env."""
    if explicit:
        return explicit
    on_path = shutil.which(name)
    if on_path:
        return on_path
    # sys.prefix is .../envs/archeon when running inside the main conda env.
    candidate = Path(sys.prefix).parent / "archeon-tools" / "bin" / name
    if candidate.is_file():
        return str(candidate)
    return None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sugar_dir: Path
    colmap_bin: str | None
    ffmpeg_bin: str | None
    ffprobe_bin: str | None
    python_bin: str
    host: str
    port: int
    max_upload_mb: int

    @property
    def scenes_dir(self) -> Path:
        return self.data_dir / "scenes"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "archeon.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = {**_load_dotenv(REPO_ROOT / ".env"), **os.environ}

    def path(key: str, default: Path) -> Path:
        value = env.get(key)
        return Path(value).expanduser().resolve() if value else default

    return Settings(
        data_dir=path("ARCHEON_DATA_DIR", REPO_ROOT / "data"),
        sugar_dir=path("ARCHEON_SUGAR_DIR", REPO_ROOT / "third_party" / "SuGaR"),
        colmap_bin=_find_tool("colmap", env.get("ARCHEON_COLMAP")),
        ffmpeg_bin=_find_tool("ffmpeg", env.get("ARCHEON_FFMPEG")),
        ffprobe_bin=_find_tool("ffprobe", env.get("ARCHEON_FFPROBE")),
        python_bin=env.get("ARCHEON_PYTHON", sys.executable),
        host=env.get("ARCHEON_HOST", "0.0.0.0"),
        port=int(env.get("ARCHEON_PORT", "8000")),
        max_upload_mb=int(env.get("ARCHEON_MAX_UPLOAD_MB", "4096")),
    )
