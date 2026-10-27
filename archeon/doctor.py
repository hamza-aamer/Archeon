"""Environment checks, shown by `archeon doctor` and summarised in the web UI."""

from __future__ import annotations

import importlib
import subprocess
from functools import lru_cache

from .config import Settings


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _first_line(cmd: list[str]) -> tuple[bool, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (out.stdout or out.stderr).strip().splitlines()
    return out.returncode == 0, text[0] if text else ""


@lru_cache(maxsize=1)
def _gpu() -> dict:
    ok, line = _first_line(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    return _check("NVIDIA GPU", ok and bool(line), line or "nvidia-smi not available")


def gpu_stats() -> dict | None:
    """Live utilisation for the UI. None when nvidia-smi is unavailable."""
    ok, line = _first_line(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
                            "temperature.gpu,power.draw", "--format=csv,noheader,nounits"])
    if not ok or not line:
        return None
    name, util, used, total, temp, power = [part.strip() for part in line.split(",")]

    def number(text: str) -> float | None:
        try:
            return float(text)
        except ValueError:
            return None

    return {"name": name, "utilization": number(util), "memory_used_mb": number(used),
            "memory_total_mb": number(total), "temperature_c": number(temp), "power_w": number(power)}


def run_checks(settings: Settings, deep: bool = True) -> list[dict]:
    checks = [_gpu()]
    checks.append(_check("SuGaR checkout", (settings.sugar_dir / "sugar_trainers").is_dir(), str(settings.sugar_dir)))
    for label, binary, args in (("COLMAP", settings.colmap_bin, ["help"]),
                                ("ffmpeg", settings.ffmpeg_bin, ["-version"]),
                                ("ffprobe", settings.ffprobe_bin, ["-version"])):
        if not binary:
            checks.append(_check(label, False, "not found (run scripts/setup.sh or set it in .env)"))
        elif deep:
            ok, line = _first_line([binary, *args])
            checks.append(_check(label, ok, f"{binary} - {line}"))
        else:
            checks.append(_check(label, True, binary))
    if not deep:
        return checks

    try:
        import torch

        cuda = torch.cuda.is_available()
        detail = f"torch {torch.__version__}, CUDA {torch.version.cuda}"
        if cuda:
            props = torch.cuda.get_device_properties(0)
            detail += f", {props.name} ({props.total_memory / 2**30:.1f} GB, sm_{props.major}{props.minor})"
        checks.append(_check("PyTorch CUDA", cuda, detail))
    except Exception as exc:
        checks.append(_check("PyTorch CUDA", False, str(exc)))

    for module in ("diff_gaussian_rasterization", "simple_knn._C", "pytorch3d", "nvdiffrast.torch", "open3d"):
        try:
            importlib.import_module(module)
            checks.append(_check(f"python: {module}", True))
        except Exception as exc:
            checks.append(_check(f"python: {module}", False, str(exc).splitlines()[0] if str(exc) else repr(exc)))
    return checks


def versions(settings: Settings) -> dict:
    """Software versions for the System page."""
    import platform
    import sys

    info = {"python": sys.version.split()[0], "platform": platform.platform()}
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info["compute_capability"] = f"{props.major}.{props.minor}"
    except Exception:
        pass
    for module in ("pytorch3d", "open3d", "numpy"):
        try:
            info[module] = importlib.import_module(module).__version__
        except Exception:
            pass
    if settings.colmap_bin:
        ok, line = _first_line([settings.colmap_bin, "help"])
        info["colmap"] = line.replace("COLMAP ", "").split(" (")[0] if ok else None
    if settings.ffmpeg_bin:
        ok, line = _first_line([settings.ffmpeg_bin, "-version"])
        info["ffmpeg"] = line.split()[2] if ok and len(line.split()) > 2 else None
    head = settings.sugar_dir / ".git"
    ok, line = _first_line(["git", "-C", str(settings.sugar_dir), "rev-parse", "--short", "HEAD"]) if head.exists() else (False, "")
    info["sugar_commit"] = line if ok else None
    ok, line = _first_line(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    info["driver"] = line if ok else None
    return info
