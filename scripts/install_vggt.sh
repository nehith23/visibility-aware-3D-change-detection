#!/usr/bin/env bash
# Installs VGGT (facebookresearch/vggt) as an editable package in third_party/.
# Run after installing PyTorch with CUDA.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p third_party
VGGT_COMMIT=a288dd0f14786c93483e45524328726ab7b1b4ce   # the version this project was tested with
if [ ! -d third_party/vggt ]; then
  git clone https://github.com/facebookresearch/vggt.git third_party/vggt
  git -C third_party/vggt checkout --quiet "$VGGT_COMMIT"
fi
pip install -e third_party/vggt
python -c "import vggt; print('vggt installed')"
echo "The model weights (facebook/VGGT-1B, about 5 GB) download on the first run."
