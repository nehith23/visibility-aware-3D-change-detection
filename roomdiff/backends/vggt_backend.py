"""Joint reconstruction of both recordings with VGGT.

Feeding the keyframes of *both* videos into a single forward pass puts every
camera and every depth map in one coordinate frame, so no separate
registration step is needed. VGGT returns world-to-camera extrinsics (OpenCV
convention, first image = identity), intrinsics, dense depth and confidence.

Memory is the constraint. Peak use grows linearly with the number of image
tokens (frames x patches). On cards under 16 GB the aggregator weights are
stored in bfloat16 (it runs under bf16 autocast anyway), which frees about
1.8 GB for frames, and the resolution drops to 392 px if 518 px would leave
too few frames per video.

Install: scripts/install_vggt.sh or scripts/setup_windows.ps1.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from ..scene import Frame, Scan

log = logging.getLogger("roomdiff")

# Measured on an RTX 4070 Laptop (8 GB) with the aggregator in bf16:
# 40 frames x 453 tokens peaked at 4.7 GB, 28 frames x 1374 tokens at 7.0 GB,
# i.e. about 0.1 MB per image token on top of the weights. An out-of-memory
# error still falls back to fewer frames, see reconstruct().
GB_PER_TOKEN = 0.10e-3
FIXED_GB = 0.3             # CUDA context and allocator slack
WEIGHTS_FP32_GB = 5.0
WEIGHTS_MIXED_GB = 3.2     # aggregator in bf16, heads in fp32
DEFAULT_FRAMES_PER_VIDEO = 40   # enough that every spot is seen several times


def _target_size(w: int, h: int, max_side: int) -> tuple[int, int]:
    s = max_side / max(w, h)
    nw = max(14, int(round(w * s / 14)) * 14)
    nh = max(14, int(round(h * s / 14)) * 14)
    return nw, nh


def _square(sizes) -> bool:
    """VGGT was trained on landscape and square images. Its own "pad"
    preprocessing turns every image into a white-padded square; feeding a
    narrow portrait frame instead makes it predict wildly anisotropic
    intrinsics (fx 195 vs fy 466 on a 224x392 iPhone frame) and inconsistent
    depth. So any portrait input goes onto a square canvas."""
    return any(h > w for w, h in sizes)


def _canvas(sizes: list[tuple[int, int]], max_side: int) -> tuple[int, int]:
    if _square(sizes):
        return max_side, max_side
    t = [_target_size(w, h, max_side) for w, h in sizes]
    return max(a for a, _ in t), max(b for _, b in t)


def gpu_memory_gb() -> tuple[float, str]:
    try:
        import torch
    except ImportError:
        return 0.0, "no torch"
    if not torch.cuda.is_available():
        return 0.0, "cpu"
    p = torch.cuda.get_device_properties(0)
    return p.total_memory / 1e9, p.name


def free_gpu_gb() -> float | None:
    """Free memory right now. On a laptop the Windows desktop already holds
    some of the VRAM, so this is the honest budget."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.mem_get_info(0)[0] / 1e9
    except Exception:  # noqa: BLE001
        pass
    return None


def plan(sizes_before: list[tuple[int, int]], sizes_after: list[tuple[int, int]],
         frames_per_video: int = 0, max_side: int = 0) -> dict:
    """Choose resolution, frame count and weight precision for this GPU."""
    gb, name = gpu_memory_gb()
    half = 0 < gb < 16
    free = free_gpu_gb()
    budget = gb * 0.88 if free is None else min(gb * 0.88, free * 0.95)
    usable = budget - (WEIGHTS_MIXED_GB if half else WEIGHTS_FP32_GB) - FIXED_GB
    sizes = sizes_before + sizes_after
    mixed = len({w > h for w, h in sizes}) > 1
    if mixed:
        log.warning("One video is portrait and the other landscape. That works, but every frame is "
                    "padded to a square, which costs about 75% more GPU memory per frame, so fewer "
                    "frames fit. Record both the same way round.")
    elif _square(sizes):
        log.info("portrait video: frames are padded to a square, as VGGT's own preprocessing does")

    def per_pass(side):
        W, H = _canvas(sizes, side)
        tokens = (W // 14) * (H // 14) + 5
        return int(usable / (tokens * GB_PER_TOKEN))

    side = max_side or (518 if gb else 392)
    cap = int(np.clip(per_pass(side), 12, 160)) if gb else 16
    n = frames_per_video or DEFAULT_FRAMES_PER_VIDEO
    passes = 1 if 2 * n <= cap else int(np.ceil((2 * n - 8) / max(cap - 8, 1)))
    out = {"gpu": name, "gpu_gb": round(gb, 1), "max_side": side, "frames_per_video": n,
           "frames_per_pass": cap, "passes": passes, "bf16_aggregator": half,
           "mixed_orientation": mixed, "canvas": _canvas(sizes, side)}
    log.info("plan: %s (%.0f GB) -> %d frames per video at %d px, up to %d frames per pass "
             "(about %d pass%s), canvas %dx%d%s", name, gb, n, side, cap, passes,
             "" if passes == 1 else "es", *out["canvas"], ", aggregator weights in bf16" if half else "")
    return out


def _load_upright(p: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def _prepare(paths: list[Path], max_side: int):
    """Resize every image so its long side is `max_side` and both sides are
    multiples of 14 (the ViT patch size). If the two videos differ in
    orientation, pad to a common canvas with white, as VGGT's own "pad"
    preprocessing does. Padding is marked invalid and never used."""
    sizes, imgs = [], []
    for p in paths:
        im = _load_upright(p)
        nw, nh = _target_size(*im.size, max_side)
        sizes.append((im.size, (nw, nh)))
        imgs.append(np.asarray(im.resize((nw, nh), Image.BICUBIC)))
    W, H = _canvas([s[0] for s in sizes], max_side)
    W, H = max(W, max(i.shape[1] for i in imgs)), max(H, max(i.shape[0] for i in imgs))
    canvas, valid, affine = [], [], []
    for im, ((fw, fh), (nw, nh)) in zip(imgs, sizes):
        oy, ox = (H - nh) // 2, (W - nw) // 2
        c = np.full((H, W, 3), 255, np.uint8)
        c[oy:oy + nh, ox:ox + nw] = im
        v = np.zeros((H, W), bool)
        v[oy:oy + nh, ox:ox + nw] = True
        canvas.append(c)
        valid.append(v)
        sx, sy = fw / nw, fh / nh
        affine.append((sx, -ox * sx, sy, -oy * sy))
    return np.stack(canvas), np.stack(valid), affine


STITCH_INFO: dict = {}


def reconstruct(before_frames: list[Path], after_frames: list[Path], max_side: int = 518,
                bf16_aggregator: bool | None = None, capacity: int = 0) -> list[Scan]:
    """capacity = most frames per VGGT pass (0 = all in one pass)."""
    import torch
    from vggt.models.vggt import VGGT
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    if torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    else:
        device, dtype = "cpu", torch.float32
    if bf16_aggregator is None:
        bf16_aggregator = device == "cuda" and gpu_memory_gb()[0] < 16

    paths = list(before_frames) + list(after_frames)
    imgs, valid, affine = _prepare(paths, max_side)
    log.info("VGGT on %d frames at %dx%d (%s)", len(paths), imgs.shape[2], imgs.shape[1], device)

    try:
        model = VGGT.from_pretrained("facebook/VGGT-1B")
    except Exception as e:  # noqa: BLE001 - flaky network: use the cached weights
        log.warning("Hugging Face unreachable (%s); using cached weights", type(e).__name__)
        model = VGGT.from_pretrained("facebook/VGGT-1B", local_files_only=True)
    model = model.eval()
    if bf16_aggregator:
        model.aggregator.to(dtype)          # runs under bf16 autocast anyway
    model = model.to(device)

    def forward(sel):
        x = torch.from_numpy(imgs[sel]).permute(0, 3, 1, 2).float().div(255).to(device)[None]
        with torch.no_grad():
            if device == "cuda":
                with torch.autocast(device_type="cuda", dtype=dtype):
                    tokens, ps_idx = model.aggregator(x)
            else:
                tokens, ps_idx = model.aggregator(x)
            # heads run without autocast, exactly as VGGT.forward does
            pose_enc = model.camera_head(tokens)[-1]
            extr, intr = pose_encoding_to_extri_intri(pose_enc, x.shape[-2:])
            depth, conf = model.depth_head(tokens, images=x, patch_start_idx=ps_idx)
        return (extr[0].float().cpu().numpy(), intr[0].float().cpu().numpy(),
                depth[0, ..., 0].float().cpu().numpy(), conf[0].float().cpu().numpy())

    from .stitch import stitched_forward

    nb = len(before_frames)
    cap = capacity or len(paths)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    oom = (torch.cuda.OutOfMemoryError,) if device == "cuda" else ()
    T_wc, K, depth, conf01, info = stitched_forward(nb, len(paths) - nb, cap, valid, forward, oom)
    if device == "cuda":
        log.info("VGGT done: %d frames in %d pass(es), peak GPU memory %.1f GB",
                 len(paths), info["passes"], torch.cuda.max_memory_allocated() / 1e9)
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    depth = np.where(valid, depth, 0).astype(np.float32)
    STITCH_INFO.clear()
    STITCH_INFO.update(info)

    frames = []
    for i, p in enumerate(paths):
        frames.append(Frame(imgs[i], depth[i], conf01[i], K[i], T_wc[i],
                            str(p), affine[i], valid[i]))
    return [Scan("before", frames[:nb]), Scan("after", frames[nb:])]
