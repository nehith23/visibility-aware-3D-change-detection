# Setup, commands and tested versions

## Tested environment

All real results were produced on this setup.

| | |
|---|---|
| Machine | Windows 11 laptop, NVIDIA GeForce RTX 4070 Laptop GPU (8 GB), 32 GB RAM |
| Python | 3.12.6 |
| PyTorch | 2.11.0+cu128, torchvision 0.26.0+cu128 |
| VGGT | facebookresearch/vggt at commit `a288dd0f14786c93483e45524328726ab7b1b4ce` (the setup scripts check out this commit); weights `facebook/VGGT-1B`, downloaded on first run (about 5 GB) |
| CLIP | open_clip_torch 3.3.0, `ViT-B-32` / `laion2b_s34b_b79k` |
| Other | numpy 1.26.4 (VGGT needs numpy below 2), opencv-python 4.11.0.86, scipy 1.17.1, scikit-learn 1.9.1, plotly 7.1.0, matplotlib 3.11.2, pillow 12.3.0 |
| Phone | iPhone 15 Pro. Room: landscape, 0.5x lens, 1080p 30 fps. Corridor: portrait, 1x lens, 1080p 30 fps. |

The steps after reconstruction (`reanalyse`, `demo`, the tests) were also run on Linux without a GPU.

## Windows (the setup I used)

```
powershell -ExecutionPolicy Bypass -File scripts\run_all_windows.ps1 -Height 1.20 -Pairs "mine=data\before.mov,data\after.mov"
```

On the first run this creates `.venv`, installs PyTorch with CUDA, the requirements and VGGT. It checks that the input videos exist, reconstructs every pair, analyses it, and stops at the first error. Several pairs can be given separated by `;`. `scripts\setup_windows.ps1` does only the installation.

## Linux

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
bash scripts/install_vggt.sh
python -m roomdiff run --before data/before.mov --after data/after.mov --out results/mine --camera-height 1.20
```

The GPU reconstruction was only run on Windows.

## Commands

| command | what it does | GPU |
|---|---|---|
| `python -m roomdiff check before.mov after.mov` | scores the footage: blur, blank walls, gaps, turning on the spot | no |
| `python -m roomdiff run --before ... --after ... --out ...` | the whole pipeline | yes |
| `python -m roomdiff reconstruct ...` | only the GPU step; writes `recon.npz` and keyframes | yes |
| `python -m roomdiff reanalyse --out ...` | everything after the GPU step, from a saved `recon.npz` | no |
| `python -m roomdiff demo` | synthetic room with known answers; scores itself | no |
| `python -m roomdiff doctor` | checks the install and shows how many frames fit on your GPU | no |

| flag | default | meaning |
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
| `report.md`, `report.json` | the list of changes; the JSON also has boxes, the evidence behind each score, and every candidate a filter rejected, with the reason |
| `*.ply` | point clouds for MeshLab or CloudCompare |

## Reproducing the results

| what | command | needs |
|---|---|---|
| the room_A or corridor_right example | `python scripts/try_example.py [room_A or corridor_right]` | CPU; CLIP weights download on first use |
| every room and corridor result from the videos | `run_room.bat` / `run_corridor.bat` | GPU; `room_videos.zip` and `corridor_videos.zip` from the release, unzipped into `data\` |
| the baseline comparison | `python scripts/ablation.py examples/ground_truth.json` | CPU; `reconstructions.zip` from the release, unzipped into `examples\` |
| the freeze check | `python scripts/verify_freeze.py` | nothing |
| the synthetic room | `python -m roomdiff demo` | CPU |

`--no-clip` changes more than the names. CLIP similarity is one of the costs used to link a removal to an addition, and CLIP also discards candidates that look like bare wall or floor. On room_A, without CLIP, the wrong jug link scores 0.54 instead of 0.44 and becomes confident.
