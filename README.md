<p align="center"><img src="web/assets/logo.png" alt="Archeon" width="360"></p>

<p align="center"><b>Walk around a space with your phone. Get a 3D Gaussian-splat scene and a textured mesh you can explore in the browser or in VR.</b></p>

Archeon is a local, GPU-backed pipeline with a web interface. Upload or record a video, and Archeon:

1. recovers the camera path with **COLMAP**,
2. trains **3D Gaussian Splatting**,
3. runs **SuGaR** to extract a textured mesh.

Results open in an in-browser viewer with WebXR VR support, and download as `.ply` / `.splat` / `.obj` / `.glb`.

```
 video ──▶ frames ──▶ COLMAP ──▶ 3D Gaussian Splatting ──▶ SuGaR ──────────────────▶ export
          (sharpest   (camera     (vanilla 3DGS,            coarse ▶ mesh ▶ refine     .ply  .splat
           per window) poses)      7k iterations)           ▶ texture                  .obj  .glb
```

Everything runs on one machine: a FastAPI server serves the UI, and a single worker processes scenes one at a time.

## Requirements

### Hardware

Archeon needs an **NVIDIA GPU with CUDA**. How much VRAM depends on the preset:

| Preset | Output | Frames · resolution | Min VRAM | Recommended | Estimated time* |
|---|---|---|---|---|---|
| **Preview** | Gaussian splat | ≤150 · 1600 px | 8 GB | 12 GB | 10–20 min |
| **Standard** (default) | splat + SuGaR textured mesh (200k vertices) | ≤200 · 1600 px | 16 GB | 24 GB | 1–1.5 h |
| **High** | splat + high-poly SuGaR mesh (1M vertices) | ≤300 · 1600 px | 24 GB | 32 GB | 1.5–3 h |

\*On a GPU that meets the recommendation. These are estimates, not measurements, except where the verification status below says otherwise.

The presets follow the upstream defaults: 3DGS's 1600 px cap and SuGaR's 15,000 refinement iterations. They are **not** shrunk to fit small GPUs. The 3DGS authors specify 24 GB for full-quality training. SuGaR adds its own models on top and keeps every training frame on the GPU. Below a preset's minimum, expect an out-of-memory error. The UI shows how your GPU compares on the **New capture** and **System** pages.

The software stack is PyTorch 2.0.1 + CUDA 11.8 (SuGaR's tested versions). That covers GPUs up to compute capability 9.0: RTX 20/30/40-series, A100, H100. RTX 50-series cards need a newer stack.

### Software

- Linux, or **WSL2** on Windows
- NVIDIA driver with CUDA 11.8+ support (`nvidia-smi` must work)
- `conda` (Miniconda or Miniforge), `git`, `gcc` ≤ 11, ~15 GB of free disk

### Verification status

Everything below was run on an **RTX 4060 Laptop GPU (8 GB)** under WSL2:

| What | Result |
|---|---|
| `archeon doctor` (GPU, COLMAP CUDA, ffmpeg, PyTorch CUDA, all CUDA extensions) | 11/11 checks pass |
| **Preview** on a 50-frame capture (instant-ngp "fox", 1080×1920) | ✅ **12 min 16 s** total. COLMAP placed 50/50 frames in 25 s; 3DGS took 11 min 51 s and produced 256k Gaussians. Viewed in the browser |
| **Preview** on the original 2.4 s app capture (72 frames) | ✅ 7.7 min. Only 696 sparse points: the clip mostly rotates in place, so quality is poor, as expected |
| Mesh viewer + `archeon import` on an archived 2025 SuGaR mesh (640k vertices, 1.2M faces) | ✅ |
| Interrupt → resume (server restarted mid-training), cancel, delete | ✅ |
| SuGaR stages (Standard / High) | ⚠️ **Not run end to end on this machine.** All SuGaR entry points import and the pipeline wiring is unit-tested, but the 8 GB GPU is below the Standard minimum. Run them on a GPU that meets the requirements |

## Setup

```bash
git clone --recursive <this repo> Archeon
cd Archeon
scripts/setup.sh
```

`setup.sh` is idempotent. It:

1. checks out SuGaR (`third_party/SuGaR`, pinned to `7c10c4a`)
2. creates two conda environments:
   - **`archeon`**: Python 3.9, PyTorch 2.0.1/cu118, PyTorch3D 0.7.4, the CUDA toolkit, the server.
   - **`archeon-tools`**: COLMAP 4.2.1 (CUDA) and ffmpeg. They are kept apart because COLMAP's CUDA 12 libraries conflict with the CUDA 11.8 PyTorch stack.
3. compiles `diff-gaussian-rasterization`, `simple-knn` and `nvdiffrast` for your GPU
4. writes `.env` with the tool paths and runs `archeon doctor`

**Slow PyPI downloads** (common from South Asia): use a nearer mirror. From Pakistan, Tsinghua measured roughly 15× faster than PyPI's CDN. The setting applies only to the `archeon` env.

```bash
ARCHEON_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple scripts/setup.sh
```

## Run

```bash
conda activate archeon
archeon serve            # http://localhost:8000
```

| Page | What it is for |
|---|---|
| **Library** | All scenes, with filters, search and live progress on cards |
| **New capture** | Upload or record a video, pick a preset (each shows whether it fits your GPU) |
| **Scene** | Live pipeline view while processing (stages, ETA, GPU, selected frames, COLMAP camera path, log). When finished: splat / mesh / camera viewer with VR mode, downloads, stats and timings |
| **Queue** | What is training now, what is next, and recent runs |
| **System** | Live GPU telemetry, which presets this GPU can run, full diagnostics with versions, storage per scene (with cleanup) |
| **Guide** | How the pipeline works, how to capture, what each output is for, VR, credits |

To record straight from a phone, open `http://<your-computer's-IP>:8000` on it (same Wi-Fi) and use **Record with camera**. On WSL2 the phone can only reach the server if you [forward the port or use mirrored networking](https://learn.microsoft.com/windows/wsl/networking).

### Command line

```bash
archeon process walk.mp4 --preset preview   # run one video without the UI (shows the live log)
archeon import --name "Old scan" --ply point_cloud.ply --obj mesh.obj   # add existing results to the library
archeon doctor [--json]                     # check GPU, CUDA extensions, COLMAP, ffmpeg
```

## Outputs

Each scene lives in `data/scenes/<id>/`. The `artifacts/` folder holds:

| File | What it is |
|---|---|
| `scene.ply` | Vanilla 3DGS splat in the standard format, readable by the Unity VR viewer, SuperSplat and other 3DGS tools |
| `scene.splat` | Same splat in the compact web format, 32 bytes per Gaussian, used by the browser viewer |
| `sugar.ply` / `sugar.splat` | SuGaR's refined Gaussians, bound to the mesh surface |
| `mesh.obj` + `mesh.mtl` + `mesh.png` | SuGaR's UV-textured mesh (also bundled as `mesh.zip`) |
| `mesh.glb` | The same mesh as a single file, used by the browser mesh viewer |
| `thumbnail.jpg`, `manifest.json` | Preview image; stats, timings and the initial camera |

`work/` keeps every intermediate output (frames, COLMAP model, 3DGS and SuGaR checkpoints), which is what lets **Resume** continue a failed or interrupted scene from the stage it stopped on. Once a scene is done, the **System** page can delete its working files to reclaim space.

## Viewing in VR

- **Browser (WebXR):** in the scene viewer, click **VR**, then **Enter VR**. This works in the Meta Quest browser (open `http://<your-computer's-IP>:8000`) or in desktop Chrome/Edge with a SteamVR/Oculus Link headset.
- **Unity VR viewer (Windows):** unzip `clients/unity-vr-viewer/ArcheonViewer-win64.zip`, put a scene's `scene.ply` in the folder you run `ArcheonViewer.exe` from, and launch it. The viewer loads every `.ply` in its working directory.

## Configuration

Settings come from environment variables or `.env`:

| Variable | Default |
|---|---|
| `ARCHEON_DATA_DIR` | `./data` |
| `ARCHEON_PORT` / `ARCHEON_HOST` | `8000` / `0.0.0.0` |
| `ARCHEON_COLMAP`, `ARCHEON_FFMPEG`, `ARCHEON_FFPROBE` | found on `PATH` or in the `archeon-tools` env |
| `ARCHEON_SUGAR_DIR` | `./third_party/SuGaR` |
| `ARCHEON_MAX_UPLOAD_MB` | `4096` |

## Repository layout

```
archeon/                 Python package
  api.py                 FastAPI routes; serves web/
  worker.py              queue + stage runner (resume, cancel, progress)
  db.py                  SQLite scene store
  pipeline/              frames, colmap, gaussians (3DGS), sugar, export, splat_format
  cli.py, doctor.py
web/                     browser UI: plain ES modules, no build step
  views/                 library, capture, scene, queue, system, guide
  vendor/                three.js, GaussianSplats3D, fonts (MIT / OFL)
third_party/SuGaR        SuGaR submodule (includes the 3DGS trainer)
scripts/setup.sh         one-shot installer
tests/                   pytest suite (`pytest -m "not gpu"` runs without a GPU)
samples/capture.mp4      the original 2.4 s app capture, for smoke tests
clients/unity-vr-viewer  the original Windows VR viewer
```

## Troubleshooting

- **"COLMAP only placed N of M frames"**: the capture didn't overlap enough. Walk around the subject (don't rotate on the spot), move slowly, avoid glossy floors and blank walls, then re-record.
- **"The GPU ran out of memory"**: the preset needs more VRAM than you have (see the System page). Use **Preview**, a shorter clip, or a bigger GPU, then press **Resume**; finished stages are not repeated.
- **Extension build fails in setup**: make sure `gcc --version` is ≤ 11 and `nvidia-smi` works, then re-run `scripts/setup.sh`.
- **`undefined symbol: iJIT_NotifyEvent` when importing torch**: MKL is too new for PyTorch 2.0.1. `environment.yml` pins `mkl<2024.1`. For an older env, run `conda install -n archeon "mkl<2024.1"`.
- **WSL2**: keep data on the Linux filesystem (not `/mnt/c`). Training reads thousands of files, and the Windows mount is very slow.

## Development

```bash
conda activate archeon
pytest -m "not gpu"      # fast suite: API, worker, runner, converters
pytest -m gpu            # full Preview pipeline on samples/capture.mp4
```

## Credits

- [SuGaR](https://github.com/Anttwo/SuGaR) (Guédon & Lepetit, CVPR 2024) and [3D Gaussian Splatting](https://github.com/graphdeco-inria/gaussian-splatting) (Kerbl et al., SIGGRAPH 2023). Both are released under Inria's non-commercial research license.
- [COLMAP](https://colmap.github.io/) (BSD)
- [GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D) and [three.js](https://threejs.org/) (MIT)
- Inter, Space Grotesk and JetBrains Mono fonts (SIL OFL 1.1)

## License

Archeon's own code is under the academic license in [LICENSE](LICENSE). Third-party components keep their own licenses.
