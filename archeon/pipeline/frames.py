"""Stage 1: decode the video and keep the sharpest frame from each time window."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .base import StageContext, StageError

MIN_FRAMES = 20
OVERSAMPLE = 3  # decode this many candidates per kept frame, then keep the sharpest of each group


def probe(ffprobe: str, video: Path) -> dict:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,nb_frames:format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise StageError(f"Could not read the video file ({out.stderr.strip()[-200:]}).")
    info = json.loads(out.stdout or "{}")
    streams = info.get("streams") or []
    if not streams:
        raise StageError("The uploaded file has no video stream.")
    stream = streams[0]
    num, _, den = (stream.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": fps,
        "duration": float((info.get("format") or {}).get("duration") or 0.0),
    }


def sharpness(path: Path) -> float:
    """Variance of the Laplacian on a downscaled greyscale copy: higher means sharper."""
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("L")
        image.thumbnail((640, 640))
        g = np.asarray(image, dtype=np.float32)
    laplacian = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(laplacian.var())


def write_thumbnail(frame: Path, out: Path, long_side: int = 320, quality: int = 80) -> None:
    from PIL import Image

    with Image.open(frame) as image:
        image = image.convert("RGB")
        image.thumbnail((long_side, long_side))
        image.save(out, "JPEG", quality=quality)


def run(ctx: StageContext) -> None:
    settings, layout, preset = ctx.settings, ctx.layout, ctx.preset
    if not settings.ffmpeg_bin or not settings.ffprobe_bin:
        raise StageError("ffmpeg/ffprobe not found. Run scripts/setup.sh or set ARCHEON_FFMPEG / ARCHEON_FFPROBE.")
    video = layout.video
    if video is None:
        raise StageError("The scene has no video file.")

    info = probe(settings.ffprobe_bin, video)
    ctx.log(f"video: {info['width']}x{info['height']} @ {info['fps']:.2f} fps, {info['duration']:.1f} s")
    if info["duration"] < 2:
        raise StageError("The video is shorter than 2 seconds; record a slow walk around the subject instead.")

    native_fps = info["fps"] or 30.0
    sample_fps = min(native_fps, max(1.0, preset.max_frames * OVERSAMPLE / info["duration"]))

    candidates_dir = layout.work / "frames_candidates"
    shutil.rmtree(candidates_dir, ignore_errors=True)
    shutil.rmtree(layout.frames, ignore_errors=True)
    candidates_dir.mkdir(parents=True)
    layout.frames.mkdir(parents=True)

    side = preset.max_side
    # Fit the long side to `side` without upscaling; -2 keeps the other side even.
    scale = f"scale=w='if(gte(iw,ih),min(iw,{side}),-2)':h='if(gte(iw,ih),-2,min(ih,{side}))'"
    total_us = info["duration"] * 1e6

    def parse(line: str) -> float | None:
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            value = line.split("=", 1)[1]
            return float(value) / total_us if value.isdigit() else None
        return None

    ctx.run(
        [settings.ffmpeg_bin, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", video,
         "-vf", f"fps={sample_fps:.4f},{scale}", "-q:v", "2", "-progress", "pipe:1", "-nostats",
         candidates_dir / "%05d.jpg"],
        parser=parse, segment=(0.0, 0.7), hide=r"^[a-z_0-9]+=",
    )

    candidates = sorted(candidates_dir.glob("*.jpg"))
    if len(candidates) < MIN_FRAMES:
        raise StageError(f"Only {len(candidates)} frames could be extracted; at least {MIN_FRAMES} are needed.")

    scores = []
    for i, path in enumerate(candidates):
        ctx.check_cancelled()
        scores.append(sharpness(path))
        if i % 20 == 0:
            ctx.progress(0.7 + 0.3 * i / len(candidates))

    keep = min(preset.max_frames, len(candidates))
    picked = [int(group[np.argmax([scores[j] for j in group])])
              for group in np.array_split(np.arange(len(candidates)), keep)]
    shutil.rmtree(layout.thumbs, ignore_errors=True)
    layout.thumbs.mkdir(parents=True)
    for index, j in enumerate(picked, start=1):
        frame = layout.frames / f"frame_{index:05d}.jpg"
        shutil.move(str(candidates[j]), frame)
        write_thumbnail(frame, layout.thumbs / frame.name)
    shutil.rmtree(candidates_dir, ignore_errors=True)

    ctx.stats.update(
        video_width=info["width"], video_height=info["height"], video_duration=round(info["duration"], 2),
        frames_decoded=len(candidates), frames_selected=len(picked),
    )
    ctx.log(f"kept the sharpest {len(picked)} of {len(candidates)} decoded frames")
