"""Core data structures shared by every stage of the pipeline.

Conventions
-----------
* Cameras follow OpenCV: x right, y down, z forward.
* ``T_wc`` is a 4x4 camera-to-world transform.
* After ``geometry.to_room_frame`` the world frame is the *room frame*:
  metric units, z up, floor at z = 0, origin under the first camera of the
  "before" recording, +y pointing where that camera looked, +x to its right.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Frame:
    image: np.ndarray            # (H, W, 3) uint8, same resolution as depth
    depth: np.ndarray            # (H, W) float32, 0 means invalid
    conf: np.ndarray             # (H, W) float32 in [0, 1]
    K: np.ndarray                # (3, 3) intrinsics at depth resolution
    T_wc: np.ndarray             # (4, 4) camera to world
    full_path: str = ""          # full resolution frame on disk (for crops)
    # maps small-image pixel (u, v) to full-res pixel: (u * sx + ox, v * sy + oy)
    full_affine: tuple = (1.0, 0.0, 1.0, 0.0)
    valid: np.ndarray | None = None  # (H, W) bool, False on padding

    @property
    def hw(self) -> tuple[int, int]:
        return self.depth.shape[:2]

    @property
    def T_cw(self) -> np.ndarray:
        return np.linalg.inv(self.T_wc)

    @property
    def center(self) -> np.ndarray:
        return self.T_wc[:3, 3]


@dataclass
class Scan:
    name: str                    # "before" or "after"
    frames: list[Frame] = field(default_factory=list)

    def camera_centers(self) -> np.ndarray:
        return np.stack([f.center for f in self.frames])


def _rel(p: str, root: Path) -> str:
    """Store keyframe paths relative to the cache file, so a results folder
    can be moved to another machine and still find its frames."""
    if not p:
        return ""
    try:
        return Path(p).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p


def save_scans(path: str | Path, scans: list[Scan]) -> None:
    """Cache reconstructions so later stages can be re-run without the GPU."""
    path = Path(path)
    data = {}
    for s in scans:
        p = s.name
        data[f"{p}/image"] = np.stack([f.image for f in s.frames])
        data[f"{p}/depth"] = np.stack([f.depth for f in s.frames]).astype(np.float16)
        data[f"{p}/conf"] = np.stack([f.conf for f in s.frames]).astype(np.float16)
        data[f"{p}/K"] = np.stack([f.K for f in s.frames])
        data[f"{p}/T_wc"] = np.stack([f.T_wc for f in s.frames])
        data[f"{p}/full_path"] = np.array([_rel(f.full_path, path.parent) for f in s.frames])
        data[f"{p}/full_affine"] = np.array([f.full_affine for f in s.frames])
        data[f"{p}/valid"] = np.stack([
            f.valid if f.valid is not None else np.ones(f.hw, bool) for f in s.frames
        ])
    data["names"] = np.array([s.name for s in scans])
    np.savez_compressed(path, **data)


def load_scans(path: str | Path) -> list[Scan]:
    path = Path(path)
    z = np.load(path, allow_pickle=False)
    scans = []
    for name in z["names"]:
        n = str(name)
        frames = []
        depth = z[f"{n}/depth"].astype(np.float32)
        conf = z[f"{n}/conf"].astype(np.float32)
        for i in range(len(depth)):
            fp = str(z[f"{n}/full_path"][i])
            if fp and not Path(fp).is_absolute():
                fp = str(path.parent / fp)
            frames.append(Frame(
                image=z[f"{n}/image"][i], depth=depth[i],
                conf=conf[i], K=z[f"{n}/K"][i], T_wc=z[f"{n}/T_wc"][i],
                full_path=fp,
                full_affine=tuple(float(v) for v in z[f"{n}/full_affine"][i]),
                valid=z[f"{n}/valid"][i],
            ))
        scans.append(Scan(n, frames))
    return scans
