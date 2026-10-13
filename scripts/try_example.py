"""Rerun the analysis on a shipped example without a GPU.

    python scripts/try_example.py            # room_A, with CLIP labels
    python scripts/try_example.py --no-clip  # skip labels
    python scripts/try_example.py corridor_right

Copies the cached reconstruction and keyframes from examples/<name>/ to
results/<name>/ (so the shipped outputs stay untouched) and runs `reanalyse`.
"""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = [a for a in sys.argv[1:] if a.startswith("--")]
name = args[0] if args else "room_A"
src, dst = root / "examples" / name, root / "results" / name
if not (src / "recon.npz").exists():
    sys.exit(f"examples/{name} has no recon.npz (shipped: room_A, corridor_right)")
dst.mkdir(parents=True, exist_ok=True)
shutil.copy2(src / "recon.npz", dst / "recon.npz")
if (src / "frames").exists():
    shutil.copytree(src / "frames", dst / "frames", dirs_exist_ok=True)
cmd = [sys.executable, "-m", "roomdiff", "reanalyse", "--out", str(dst), "--camera-height", "1.20", *flags]
sys.exit(subprocess.call(cmd, cwd=root))
