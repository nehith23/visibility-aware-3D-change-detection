"""End-to-end orchestration."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from .changes import REJECTED, UNOBSERVED, assemble, detect
from .config import Config
from .describe import HEADER, describe
from .geometry import refine_alignment, to_room_frame
from .scene import Scan, load_scans, save_scans
from .semantics import annotate, counter_evidence
from . import visualize as viz

log = logging.getLogger("roomdiff")


def reconstruct_videos(before: str, after: str, out: Path, cfg: Config) -> list[Scan]:
    from .backends import vggt_backend
    from .frames import ensure_sdr, extract_keyframes, first_frame_size, resolve_input

    before = ensure_sdr(resolve_input(before), out / "videos")
    after = ensure_sdr(resolve_input(after), out / "videos")
    p = vggt_backend.plan([first_frame_size(before)], [first_frame_size(after)],
                          cfg.frames_per_video, cfg.max_side)
    (out / "plan.json").write_text(json.dumps(p, indent=2))
    fb = extract_keyframes(before, out / "frames" / "before", p["frames_per_video"])
    fa = extract_keyframes(after, out / "frames" / "after", p["frames_per_video"])
    scans = vggt_backend.reconstruct(fb, fa, p["max_side"], p["bf16_aggregator"], p["frames_per_pass"])
    p["stitch"] = vggt_backend.STITCH_INFO
    (out / "plan.json").write_text(json.dumps(p, indent=2, default=float))
    return scans


def reconstruct_only(before: str, after: str, out: str | Path, cfg: Config) -> Path:
    """GPU step only. The cached recon.npz plus frames/ is all the analysis needs."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    scans = reconstruct_videos(before, after, out, cfg)
    save_scans(out / "recon.npz", scans)
    (out / "inputs.json").write_text(json.dumps({"before": str(before), "after": str(after)}, indent=2))
    log.info("reconstruction took %.1f s, saved %s", time.time() - t, out / "recon.npz")
    return out / "recon.npz"


def analyse(scans: list[Scan], out: Path, cfg: Config, extra_summary: dict | None = None):
    """Everything after reconstruction. Pure numpy, runs on any machine."""
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    scans, room = to_room_frame(scans, cfg.camera_height, cfg.scale)
    smap = {s.name: s for s in scans}
    before, after = smap["before"], smap["after"]
    after, T_icp, icp = refine_alignment(before, after)
    smap["after"] = after
    room.update(icp)

    res = detect(before, after, cfg)
    suppressed = []
    for regions in (res.removed, res.added):
        bad = annotate(regions, smap, cfg)
        for r in bad:
            regions.remove(r)
            suppressed.append(f"{r.scan}: region at {np.round(r.box_center, 2).tolist()} "
                              f"looked like '{r.label}' ({r.label_score:.0%})")
    changes = assemble(res, cfg)
    for c in changes:
        c.description = describe(c)
    counter_evidence(changes, smap)

    summary = {
        "scale": room["scale"],
        "camera_height": cfg.camera_height,
        "floor_inlier_ratio": room["floor_inlier_ratio"],
        "alignment": {k: v for k, v in icp.items()},
        "coverage": {
            "before_verified": float(1 - (res.states["before"] == UNOBSERVED).mean()),
            "after_verified": float(1 - (res.states["after"] == UNOBSERVED).mean()),
        },
        "point_states": res.stats,
        "suppressed": suppressed,
        "rejected_by_filters": list(REJECTED),
        "config": cfg.to_dict(),
        **(extra_summary or {}),
    }
    viz.scene_html(res, changes, smap, out / "scene.html", summary)
    viz.topdown_png(res, changes, smap, out / "topdown.png")
    viz.evidence_png(changes, out / "evidence.png")
    for name in ("before", "after"):
        viz.write_ply(out / f"cloud_{name}.ply", *res.clouds[name])
    viz.write_ply(out / "changes.ply", *viz.change_cloud(res, changes))
    data = viz.report(changes, summary, out, HEADER)
    np.save(out / "T_room_recon.npy", room["T_room_recon"])
    log.info("analysis took %.1f s", time.time() - t0)

    print("\n" + "=" * 70)
    print(f"{sum(c.confident for c in changes)} confident change(s), {sum(not c.confident for c in changes)} low-confidence  |  'before' re-observed: "
          f"{100 * summary['coverage']['before_verified']:.0f}%")
    for c in changes:
        mark = "" if c.confident else "  (low confidence)"
        print(f"  #{c.id} {c.kind:<8} [{c.confidence:.2f}] {c.description}{mark}")
    if suppressed:
        print(f"  ({len(suppressed)} candidate(s) suppressed as likely artefacts, see report.md)")
    print(f"\nOpen {out / 'scene.html'} for the interactive 3D view.")
    print("=" * 70)
    return changes, data, room, res


def run(before: str, after: str, out: str | Path, cfg: Config, force: bool = False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "recon.npz"
    if cache.exists() and not force:
        log.info("using cached reconstruction %s (pass --force to redo)", cache)
        scans = load_scans(cache)
    else:
        t = time.time()
        scans = reconstruct_videos(before, after, out, cfg)
        save_scans(cache, scans)
        log.info("reconstruction took %.1f s", time.time() - t)
    (out / "inputs.json").write_text(json.dumps({"before": str(before), "after": str(after)}, indent=2))
    return analyse(scans, out, cfg)
