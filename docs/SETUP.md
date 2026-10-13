# Setup and commands

The README covers the setup I used (Windows laptop, NVIDIA GPU). This page has the alternatives and the full command list. Tested versions are in [ENVIRONMENT.md](ENVIRONMENT.md).

## Linux

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
bash scripts/install_vggt.sh
python -m roomdiff run --before data/before.mov --after data/after.mov --out results/mine --camera-height 1.20
```

The analysis steps were run on Linux; the GPU reconstruction was only run on Windows.

## Google Colab

`notebooks/colab.ipynb` runs the corridor comparisons on a free Colab GPU. Zip the repo with the videos in `data/corridor/`, put it in a Drive folder called `roomdiff_data`, and run all cells. Not tested end to end.

## Commands

| command | what it does | GPU |
|---|---|---|
| `python -m roomdiff check before.mov after.mov` | scores the footage before you spend GPU time: blur, blank walls, gaps, turning on the spot | no |
| `python -m roomdiff run --before ... --after ... --out ...` | the whole pipeline | yes |
| `python -m roomdiff reconstruct ...` | only the GPU step; writes `recon.npz` and keyframes | yes |
| `python -m roomdiff reanalyse --out ...` | everything after the GPU step, from a saved `recon.npz` | no |
| `python -m roomdiff demo` | synthetic room with known answers, scores itself | no |
| `python -m roomdiff doctor` | checks the install and shows how many frames fit on your GPU | no |
| `python scripts/try_example.py` | reruns a shipped example (room_A or corridor_right) | no |
| `python scripts/ablation.py examples/ground_truth.json` | the baseline comparison in `examples/ablation.md` | no |
| `python scripts/verify_freeze.py` | checks the detection code still matches the frozen hashes | no |

## Settings

| flag | default | when to change it |
|---|---|---|
| `--camera-height` | 1.35 | phone height above the floor in metres; sets the real-world scale |
| `--frames` | from GPU memory | frames per video |
| `--max-side` | 518 | VGGT input size |
| `--scale` | estimated | set it if the floor is never visible |
| `--no-clip` | off | skip object names |

All thresholds are in `roomdiff/config.py`.

## Outputs

| file | content |
|---|---|
| `scene.html` | interactive 3D view with change boxes, camera paths and toggles |
| `topdown.png` | floor plan with numbered changes |
| `evidence.png` | before and after image crops for each change |
| `report.md`, `report.json` | the list of changes; the JSON also has boxes, the evidence behind each score, and every candidate a filter rejected with the reason |
| `*.ply` | point clouds for MeshLab or CloudCompare |

## Reproducing from the videos

Download the videos from the release and unzip them into `data\`. Then `run_room.bat` (room) or `run_all.bat` (corridor) sets up the environment, reconstructs and analyses every comparison, and stops at the first error.
