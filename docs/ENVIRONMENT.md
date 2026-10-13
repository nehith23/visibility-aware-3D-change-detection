# Tested environment

Every real result in this repository was produced on this setup.

| | |
|---|---|
| Machine | Windows 11 laptop, NVIDIA GeForce RTX 4070 Laptop GPU (8 GB), 32 GB RAM |
| Python | 3.12.6 |
| PyTorch | 2.11.0+cu128, torchvision 0.26.0+cu128 |
| VGGT | facebookresearch/vggt at commit `a288dd0f14786c93483e45524328726ab7b1b4ce` (the setup scripts check out this commit) |
| VGGT weights | `facebook/VGGT-1B` from Hugging Face, downloaded on first run (about 5 GB) |
| CLIP | open_clip_torch 3.3.0, `ViT-B-32` / `laion2b_s34b_b79k` |
| Other | numpy 1.26.4 (VGGT needs numpy below 2), opencv-python 4.11.0.86, scipy 1.17.1, scikit-learn 1.9.1, plotly 7.1.0, matplotlib 3.11.2, pillow 12.3.0, huggingface_hub 2.2.0 |
| Phone | iPhone 15 Pro. Corridor: portrait, 1x lens, 1080p 30 fps SDR. Room: landscape, 0.5x lens, 1080p 30 fps SDR. |

The analysis step (`reanalyse`, `demo`, tests) is pure numpy and was also run on Linux (Python 3.13, no GPU). Results there match the laptop's except for labels when CLIP is off.

## Reproducing the numbers

| what | command | needs |
|---|---|---|
| room_A or corridor_right outputs from the shipped reconstruction and keyframes | `python scripts/try_example.py [room_A or corridor_right]` | CPU; CLIP weights for labels |
| same, without labels | add `--no-clip` | CPU only |
| all corridor and room results from the videos | `run_all.bat` (corridor) / `run_room.bat` (room), or `python -m roomdiff run ...` per pair | NVIDIA GPU; `corridor_videos.zip` and `room_videos.zip` from the release unzipped into `data\` |
| ablation table | `python scripts/ablation.py examples/ground_truth.json` | CPU; `reconstructions.zip` from the release unzipped into `examples/` |
| freeze check | `python scripts/verify_freeze.py` | nothing |
| synthetic room | `python -m roomdiff demo` | CPU |

`--no-clip` changes more than the names. Move matching uses CLIP similarity as one of its costs, and CLIP also suppresses candidates that look like bare wall or floor. Without it the corridor_right pair gives the same confident changes, but the backpack move scores 0.60 instead of 0.55, and a few wall-like candidates stay in the low-confidence list instead of being suppressed.
