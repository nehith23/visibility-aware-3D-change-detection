"""Command line entry point.

    python -m roomdiff check before.mov after.mov   # is the footage good enough?
    python -m roomdiff run --before before.mov --after after.mov --out results/room
    python -m roomdiff reconstruct ...              # GPU step only, writes recon.npz
    python -m roomdiff reanalyse --out results/room # re-run detection, no GPU
    python -m roomdiff demo                         # synthetic room, no GPU needed
    python -m roomdiff doctor                       # check your environment
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import Config


def _cfg(a) -> Config:
    cfg = Config()
    if getattr(a, "frames", None):
        cfg.frames_per_video = a.frames
    if getattr(a, "camera_height", None):
        cfg.camera_height = a.camera_height
    if getattr(a, "scale", None):
        cfg.scale = a.scale
    if getattr(a, "no_clip", False):
        cfg.use_clip = False
    if getattr(a, "max_side", None):
        cfg.max_side = a.max_side
    return cfg


def cmd_run(a):
    from .pipeline import run
    run(a.before, a.after, a.out, _cfg(a), force=a.force)


def cmd_reconstruct(a):
    from .pipeline import reconstruct_only
    reconstruct_only(a.before, a.after, a.out, _cfg(a))


def cmd_check(a):
    from .frames import check_video, resolve_input
    reps = []
    for v in a.videos:
        r = check_video(resolve_input(v))
        reps.append(r)
        print(f"\n{r['file']}: {r['width']}x{r['height']} {r['orientation']}, {r['duration_s']} s")
        print(f"  blurry frames {100 * r['blurry_share']:.0f}%, longest gap without a usable frame "
              f"{r['longest_blurry_gap_s']} s, blank-surface footage {100 * r['low_texture_share']:.0f}%, "
              f"rotation-only score {r['rotation_only_score']} (1.0 = turned on the spot)")
        for t in r["tips"]:
            print(f"  - {t}")
        print(f"  verdict: {r['verdict'].upper()}")
    if len(reps) > 1 and len({r['orientation'] for r in reps}) > 1:
        print("\n  - The videos differ in orientation. Record them all the same way round.")
    if len(reps) > 1 and len({(r['width'], r['height']) for r in reps if r['orientation'] == reps[0]['orientation']}) > 1:
        print("\n  - The videos differ in resolution. Use the same camera settings for both.")


def cmd_reanalyse(a):
    from .pipeline import analyse
    from .scene import load_scans
    out = Path(a.out)
    analyse(load_scans(out / "recon.npz"), out, _cfg(a))


def cmd_demo(a):
    from .backends.synthetic import generate
    from .evaluate import evaluate
    from .pipeline import analyse

    out = Path(a.out)
    cfg = _cfg(a)
    cfg.use_clip = False          # flat synthetic boxes mean nothing to CLIP
    print("Rendering a synthetic room with known changes ...")
    scans, meta = generate(out / "frames", n_frames=a.frames or 28)
    changes, data, room, res = analyse(scans, out, cfg, {"input": "synthetic"})
    score = evaluate(changes, res, meta, room["T_room_recon"])
    (out / "evaluation.json").write_text(json.dumps(score, indent=2))
    print("\nGround truth check")
    for r in score["per_change"]:
        status = (f"found ({'confident' if r['confident'] else 'low confidence'} {r['confidence']:.2f}), "
                  f"error {r['xy_error_m']:.2f} m horizontal, {r['z_error_m']:.2f} m vertical") if r["found"] else "MISSED"
        turn = f", turn true {r['true_turn']:.0f} / est {r['est_turn']}" if r.get("true_turn") else ""
        print(f"  {r['type']:<8} {r['object']:<14} {status}{turn}")
    for t in score["occlusion_traps"]:
        print(f"  trap     {t['object']:<14} unchanged but never seen in 'after': "
              f"{100 * t['unobserved_share']:.0f}% marked unverified, "
              f"{'WRONGLY reported' if t['wrongly_reported'] else 'correctly not reported'}")
    a, c = score["all_candidates"], score["confident_only"]
    print(f"  all candidates:  precision {a['precision']:.2f}  recall {a['recall']:.2f}")
    print(f"  confident only:  precision {c['precision']:.2f}  recall {c['recall']:.2f}")


def cmd_doctor(_a):
    ok = True
    print(f"python {sys.version.split()[0]}")
    for mod in ("numpy", "scipy", "sklearn", "cv2", "matplotlib", "plotly", "PIL"):
        try:
            __import__(mod)
            print(f"  [ok] {mod}")
        except ImportError:
            ok = False
            print(f"  [missing] {mod}  ->  pip install -r requirements.txt")
    try:
        import torch
        print(f"  [ok] torch {torch.__version__}")
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            print(f"  [ok] CUDA GPU: {p.name}, {p.total_memory / 1e9:.1f} GB")
            from .backends.vggt_backend import plan
            logging.getLogger("roomdiff").setLevel(logging.WARNING)
            pl = plan([(1920, 1080)], [(1920, 1080)])
            print(f"       two landscape videos -> about {pl['frames_per_video']} frames per video "
                  f"at {pl['max_side']} px{', aggregator in bf16' if pl['bf16_aggregator'] else ''}")
        else:
            print("  [warn] no CUDA GPU, reconstruction will be slow on CPU")
    except ImportError:
        ok = False
        print("  [missing] torch  ->  see README, install the CUDA build of PyTorch")
    try:
        import vggt  # noqa: F401
        print("  [ok] vggt")
    except ImportError:
        ok = False
        print("  [missing] vggt  ->  bash scripts/install_vggt.sh, or scripts\\setup_windows.ps1 on Windows")
    try:
        import open_clip  # noqa: F401
        print("  [ok] open_clip (semantic labels)")
    except ImportError:
        print("  [warn] open_clip missing, labels fall back to colour and size")
    print("ready" if ok else "fix the items above, then run again")


def main(argv=None):
    p = argparse.ArgumentParser(prog="roomdiff", description="What changed in the room?")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--camera-height", type=float, help="phone height above floor in metres (default 1.35)")
        sp.add_argument("--scale", type=float, help="override metric scale factor")
        sp.add_argument("--no-clip", action="store_true", help="skip CLIP labels")

    r = sub.add_parser("run", help="compare two videos")
    r.add_argument("--before", required=True, help="video or folder of images")
    r.add_argument("--after", required=True, help="video or folder of images")
    r.add_argument("--out", default="results/run")
    r.add_argument("--frames", type=int, help="keyframes per video (default: from GPU memory)")
    r.add_argument("--force", action="store_true", help="ignore cached reconstruction")
    r.add_argument("--max-side", type=int, choices=[392, 518], help="VGGT input size")
    common(r)
    r.set_defaults(fn=cmd_run)

    rc = sub.add_parser("reconstruct", help="GPU step only: keyframes + VGGT -> recon.npz")
    rc.add_argument("--before", required=True)
    rc.add_argument("--after", required=True)
    rc.add_argument("--out", default="results/run")
    rc.add_argument("--frames", type=int, help="keyframes per video (default: from GPU memory)")
    rc.add_argument("--max-side", type=int, choices=[392, 518], help="VGGT input size")
    rc.set_defaults(fn=cmd_reconstruct)

    ck = sub.add_parser("check", help="score recordings before running anything")
    ck.add_argument("videos", nargs="+")
    ck.set_defaults(fn=cmd_check)

    ra = sub.add_parser("reanalyse", help="re-run detection on a cached reconstruction")
    ra.add_argument("--out", required=True)
    common(ra)
    ra.set_defaults(fn=cmd_reanalyse)

    d = sub.add_parser("demo", help="synthetic room with ground truth, no GPU needed")
    d.add_argument("--out", default="examples/synthetic")
    d.add_argument("--frames", type=int)
    common(d)
    d.set_defaults(fn=cmd_demo)

    sub.add_parser("doctor", help="check the environment").set_defaults(fn=cmd_doctor)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    a.fn(a)


if __name__ == "__main__":
    main()
