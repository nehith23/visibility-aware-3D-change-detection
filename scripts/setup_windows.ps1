# One-time setup on Windows with an NVIDIA GPU. From the repo folder run:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
# Creates .venv, installs PyTorch (CUDA 12.8), this repo's requirements and VGGT,
# then runs the environment check. Needs Python 3.10-3.12 and Git on PATH.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment .venv"
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip

Write-Host "Installing PyTorch with CUDA 12.8 (about 3 GB)"
& $py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

New-Item -ItemType Directory -Force -Path third_party | Out-Null
if (-not (Test-Path third_party\vggt)) {
    git clone https://github.com/facebookresearch/vggt.git third_party\vggt
    git -C third_party\vggt checkout --quiet a288dd0f14786c93483e45524328726ab7b1b4ce
}
# one resolution so VGGT's numpy<2 pin and OpenCV agree
& $py -m pip install -r requirements.txt -e third_party\vggt numpy==1.26.4

& $py -m roomdiff doctor
Write-Host ""
Write-Host "Done. Use .\.venv\Scripts\python.exe -m roomdiff ... for every command."
Write-Host "The VGGT weights (about 5 GB) download on the first reconstruction."
