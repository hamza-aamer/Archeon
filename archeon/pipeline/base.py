"""Shared plumbing for pipeline stages: scene paths, logging, progress and cancellable subprocesses."""

from __future__ import annotations

import collections
import os
import re
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..config import Settings
from ..presets import Preset

ProgressParser = Callable[[str], Optional[float]]

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_OOM = re.compile(r"CUDA out of memory|OutOfMemoryError|CUBLAS_STATUS_ALLOC_FAILED", re.I)


class StageError(Exception):
    """A stage failed with a message meant for the user."""


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class SceneLayout:
    root: Path

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def frames(self) -> Path:
        return self.work / "frames"

    @property
    def colmap(self) -> Path:
        return self.work / "colmap"

    @property
    def thumbs(self) -> Path:
        """Small copies of the selected frames, for the web UI."""
        return self.work / "thumbs"

    @property
    def dataset(self) -> Path:
        """COLMAP dataset in the layout 3DGS/SuGaR expect: images/ + sparse/0/."""
        return self.work / "dataset"

    @property
    def gs_model(self) -> Path:
        # SuGaR names its outputs after the dataset folder, so keep 3DGS output next to them.
        return self.work / "output" / "vanilla_gs" / self.dataset.name

    @property
    def sugar_state(self) -> Path:
        return self.work / "sugar_state.json"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def log(self) -> Path:
        return self.root / "log.txt"

    @property
    def video(self) -> Path | None:
        return next(iter(sorted(self.root.glob("video.*"))), None)

    def done_marker(self, stage: str) -> Path:
        return self.work / f".{stage}.done"


@dataclass
class StageContext:
    settings: Settings
    layout: SceneLayout
    preset: Preset
    cancel_event: threading.Event = field(default_factory=threading.Event)
    on_progress: Callable[[float], None] = lambda fraction: None
    stats: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    _log_lock: threading.Lock = field(default_factory=threading.Lock)

    # ----- logging / progress -----
    def write_log(self, text: str) -> None:
        with self._log_lock, open(self.layout.log, "a", encoding="utf-8") as fh:
            fh.write(text)

    def log(self, message: str) -> None:
        self.write_log(f"[archeon] {message}\n")

    def progress(self, fraction: float) -> None:
        self.on_progress(min(max(fraction, 0.0), 1.0))

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    # ----- subprocesses -----
    def run(self, cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
            parser: ProgressParser | None = None, segment: tuple[float, float] = (0.0, 1.0),
            hide: str | None = None) -> None:
        """Run a command, streaming output into the scene log and mapping parsed progress into `segment`.

        Lines matching the `hide` regex still feed the parser but are kept out of the log."""
        self.check_cancelled()
        self.log("$ " + shlex.join(str(c) for c in cmd))
        full_env = {**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})}
        proc = subprocess.Popen(
            [str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=full_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
            preexec_fn=_die_with_parent,
        )
        tail: collections.deque[str] = collections.deque(maxlen=60)
        lo, hi = segment
        hidden = re.compile(hide) if hide else None

        def pump() -> None:
            buffer = b""
            last_cr_write = 0.0
            for chunk in iter(lambda: proc.stdout.read1(65536), b""):
                buffer += chunk
                parts = re.split(rb"(\r\n|\r|\n)", buffer)
                buffer = parts.pop()  # incomplete trailing piece
                for text, sep in zip(parts[0::2], parts[1::2]):
                    line = _ANSI.sub("", text.decode("utf-8", "replace")).rstrip()
                    if not line:
                        continue
                    tail.append(line)
                    if parser:
                        fraction = parser(line)
                        if fraction is not None:
                            self.progress(lo + (hi - lo) * min(max(fraction, 0.0), 1.0))
                    if hidden and hidden.search(line):
                        continue
                    # tqdm-style redraws end in a bare \r; keep one every few seconds so the log stays readable
                    if sep == b"\r":
                        now = time.monotonic()
                        if now - last_cr_write < 3:
                            continue
                        last_cr_write = now
                    self.write_log(line + "\n")
            if buffer.strip():
                line = _ANSI.sub("", buffer.decode("utf-8", "replace")).rstrip()
                tail.append(line)
                self.write_log(line + "\n")

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            while True:
                try:
                    proc.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancel_event.is_set():
                        _terminate(proc)
                        raise Cancelled()
        finally:
            reader.join(timeout=5)

        if proc.returncode != 0:
            joined = "\n".join(tail)
            if _OOM.search(joined):
                raise StageError(
                    "The GPU ran out of memory. Try the Preview preset, or a shorter / lower-resolution video."
                )
            last = next((line for line in reversed(tail) if line.strip()), "")
            raise StageError(f"{Path(str(cmd[0])).name} {cmd[1] if len(cmd) > 1 else ''} failed "
                             f"(exit code {proc.returncode}): {last[-300:]}")


def _die_with_parent() -> None:
    """Runs in the child before exec: if the server is killed outright, take the GPU job down with it
    instead of leaving an orphaned training process holding the GPU (Linux only)."""
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
    except (OSError, AttributeError):
        pass


def _terminate(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


def fraction_parser(pattern: str, total: int | None = None, relative: bool = False) -> ProgressParser:
    """Build a parser from a regex with groups (done, total) or (done) with a fixed total.

    With relative=True, progress is measured from the first value seen, for counters that resume
    mid-way (SuGaR's coarse stage continues 3DGS's iteration count from 7000 to 15000)."""
    regex = re.compile(pattern)
    start: list[float] = []

    def parse(line: str) -> float | None:
        match = regex.search(line)
        if not match:
            return None
        done = float(match.group(1))
        denominator = float(match.group(2)) if match.lastindex and match.lastindex >= 2 else float(total or 0)
        if relative:
            if not start:
                start.append(done)
            done, denominator = done - start[0], denominator - start[0]
        return done / denominator if denominator > 0 else None

    return parse


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    weight: float
    run: Callable[[StageContext], None]
    applies: Callable[[Preset], bool] = lambda preset: True
    description: str = ""
