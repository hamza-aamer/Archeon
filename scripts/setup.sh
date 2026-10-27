#!/usr/bin/env bash
# One-time setup: SuGaR checkout, the two conda environments, CUDA extensions, and .env with tool paths.
# Safe to re-run; finished steps are skipped.
#
# Slow PyPI downloads? Point pip at a nearer mirror, e.g. from South/East Asia:
#   ARCHEON_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple scripts/setup.sh
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
info() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v conda >/dev/null || die "conda not found. Install Miniconda or Miniforge first."
command -v nvidia-smi >/dev/null || die "nvidia-smi not found. An NVIDIA GPU and driver are required."
eval "$(conda shell.bash hook)"

env_exists() { conda env list | awk '{print $1}' | grep -qx "$1"; }

if [ -n "${ARCHEON_PIP_INDEX_URL:-}" ]; then
  info "Using PyPI mirror ${ARCHEON_PIP_INDEX_URL}"
  export PIP_INDEX_URL="$ARCHEON_PIP_INDEX_URL"
fi

info "SuGaR submodule"
git submodule update --init --recursive

if ! env_exists archeon-tools; then
  info "Creating conda env 'archeon-tools' (COLMAP + ffmpeg)"
  conda env create -f environment-tools.yml
fi
if ! env_exists archeon; then
  info "Creating conda env 'archeon' (PyTorch 2.0.1 / CUDA 11.8 / PyTorch3D). This downloads ~3 GB."
  conda env create -f environment.yml
fi

conda activate archeon
if [ -n "${ARCHEON_PIP_INDEX_URL:-}" ]; then
  pip config --site set global.index-url "$ARCHEON_PIP_INDEX_URL" >/dev/null  # scoped to this env only
fi
export CUDA_HOME="$CONDA_PREFIX"
if [ -z "${TORCH_CUDA_ARCH_LIST:-}" ]; then
  TORCH_CUDA_ARCH_LIST="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d ' ')"
  export TORCH_CUDA_ARCH_LIST
fi
info "Building CUDA extensions for compute capability ${TORCH_CUDA_ARCH_LIST}"

SUBMODULES="third_party/SuGaR/gaussian_splatting/submodules"
python -c "import diff_gaussian_rasterization" 2>/dev/null \
  || pip install --no-build-isolation "$SUBMODULES/diff-gaussian-rasterization"
python -c "import simple_knn._C" 2>/dev/null \
  || pip install --no-build-isolation "$SUBMODULES/simple-knn"
python -c "import nvdiffrast.torch" 2>/dev/null \
  || pip install --no-build-isolation "https://github.com/NVlabs/nvdiffrast/archive/refs/tags/v0.3.3.tar.gz"

info "Installing the archeon package"
pip install --no-deps --no-build-isolation -e .

TOOLS_BIN="$(conda env list | awk '$1 == "archeon-tools" {print $NF}')/bin"
if [ ! -f .env ]; then
  info "Writing .env"
  cat > .env <<EOF
# Paths to external tools (written by scripts/setup.sh)
ARCHEON_COLMAP=$TOOLS_BIN/colmap
ARCHEON_FFMPEG=$TOOLS_BIN/ffmpeg
ARCHEON_FFPROBE=$TOOLS_BIN/ffprobe
# ARCHEON_DATA_DIR=$ROOT/data
# ARCHEON_PORT=8000
EOF
fi

info "Checking the installation"
archeon doctor

cat <<EOF

Done. Start Archeon with:

  conda activate archeon
  archeon serve

then open http://localhost:8000
EOF
