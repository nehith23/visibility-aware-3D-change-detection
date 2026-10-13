"""What does each part of the pipeline contribute?

Runs four detectors of increasing sophistication on cached reconstructions and
counts, per comparison, how many ground-truth change locations are hit and how
many reported regions are not near any of them (spatial false positives):

  1. nearest-neighbour diff   a point is changed if the other cloud has no point within 5 cm
  2. visibility only          free-space votes (present / gone / unobserved), no filters
  3. full pipeline, all       every candidate the pipeline reports, low confidence included
  4. full pipeline, confident only changes at or above the confidence threshold

Usage:
    python scripts/ablation.py examples/ground_truth.json

The ground truth file lists, per comparison, the recon.npz path, the camera
height and the object positions (x, y in the room frame of that comparison).
A region counts as hitting a location if its centre is within 0.5 m (xy).
This is a coarse location check: it ignores change type, object identity and
height, does not penalise several regions near one location, and cannot tell
whether a removal and an addition were paired correctly.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roomdiff.changes import GONE, assemble, detect  # noqa: E402
from roomdiff.config import Config  # noqa: E402
from roomdiff.geometry import refine_alignment, to_room_frame  # noqa: E402
from roomdiff.scene import load_scans  # noqa: E402

HIT = 0.5


def plain_clusters(pts: np.ndarray, mask: np.ndarray, cfg: Config) -> list[np.ndarray]:
    """Centres of DBSCAN clusters, with the same size floor as the pipeline."""
    p = pts[mask]
    if len(p) < cfg.min_cluster_points:
        return []
    lab = DBSCAN(eps=cfg.cluster_eps, min_samples=cfg.cluster_min_samples).fit_predict(p)
    out = []
    for k in set(lab) - {-1}:
        q = p[lab == k]
        if len(q) >= cfg.min_report_points and np.ptp(q, 0).max() >= cfg.min_cluster_extent:
            out.append(q.mean(0))
    return out


def score(centres: list[np.ndarray], gt: list[list[float]]):
    g = np.array(gt, float).reshape(-1, 2)
    hit = np.zeros(len(g), bool)
    fp = 0
    for c in centres:
        d = np.linalg.norm(g - c[:2], axis=1) if len(g) else np.array([np.inf])
        if d.min() <= HIT:
            hit[d.argmin()] = True
        else:
            fp += 1
    return int(hit.sum()), len(g), fp


def scenes(spec: dict) -> dict:
    """Scene entries of a ground-truth file. Keys starting with '_' are notes;
    anything else must be a complete scene entry."""
    out = {}
    for name, entry in spec.items():
        if name.startswith("_"):
            continue
        if not isinstance(entry, dict) or not {"recon", "camera_height", "objects"} <= entry.keys():
            raise ValueError(f"ground truth entry '{name}' needs recon, camera_height and objects")
        out[name] = entry
    return out


def run(entry: dict, root: Path) -> dict:
    cfg = Config(camera_height=entry["camera_height"], use_clip=False)
    scans = load_scans(root / entry["recon"])
    scans, _ = to_room_frame(scans, cfg.camera_height, cfg.scale)
    sm = {s.name: s for s in scans}
    after, _, _ = refine_alignment(sm["before"], sm["after"])
    sm["after"] = after
    gt = entry["objects"]

    res = detect(sm["before"], after, cfg)

    # 1. nearest-neighbour diff on exactly the clouds the visibility test uses
    #    (same voxel grid, range limit and self-support filter)
    cb, _ = res.clouds["before"]
    ca, _ = res.clouds["after"]
    nn_b = cKDTree(ca).query(cb)[0] > 0.05
    nn_a = cKDTree(cb).query(ca)[0] > 0.05
    nn = plain_clusters(cb, nn_b & (cb[:, 2] > cfg.floor_band), cfg) + \
        plain_clusters(ca, nn_a & (ca[:, 2] > cfg.floor_band), cfg)

    # 2..4 from the pipeline
    vis = []
    for name in ("before", "after"):
        pts, _ = res.clouds[name]
        vis += plain_clusters(pts, res.states[name] == GONE, cfg)
    changes = assemble(res, cfg)

    def centres(cs):
        out = []
        for c in cs:
            out.append(c.region.box_center)
            if c.target is not None:
                out.append(c.target.box_center)
        return out

    return {
        "nearest-neighbour diff": score(nn, gt),
        "visibility only": score(vis, gt),
        "full pipeline, all": score(centres(changes), gt),
        "full pipeline, confident": score(centres([c for c in changes if c.confident]), gt),
    }


def main():
    logging.basicConfig(level=logging.WARNING)
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/ground_truth.json")
    spec = json.loads(path.read_text())
    root = path.parent
    only = sys.argv[2:]
    rows = {}
    for name, entry in scenes(spec).items():
        if only and name not in only:
            continue
        if not (root / entry["recon"]).exists():
            print(f"skipping {name}: {entry['recon']} not found")
            continue
        rows[name] = run(entry, root)
        print(name, json.dumps(rows[name]), flush=True)
    methods = ["nearest-neighbour diff", "visibility only", "full pipeline, all", "full pipeline, confident"]
    print("\n| method | " + " | ".join(rows) + " |")
    print("|---|" + "---|" * len(rows))
    for m in methods:
        cells = []
        for name in rows:
            h, n, fp = rows[name][m]
            cells.append(f"{fp} spatial FP" if n == 0 else f"{h}/{n} found, {fp} spatial FP")
        print(f"| {m} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
