"""Reconstruct more frames than fit on the GPU in one pass.

VGGT's memory grows with the number of frames, and an 8 GB laptop GPU holds
about 28 square frames at 518 px. That is too few to see every part of a room
from both recordings at least twice. So the keyframes are split into several
passes. Every pass also contains the same few *anchor* frames, spread over
both recordings. Each pass comes back in its own arbitrary similarity frame
(VGGT puts the first image at the origin at an unknown scale), and the anchors
tie the passes together: an anchor's depth map in pass j and in pass 0 gives
3D points at *identical pixels*, so the similarity transform between the two
passes is a closed-form Umeyama fit on exact correspondences, no feature
matching needed.

Everything here is numpy so it can be tested without a GPU; the model call is
injected as `forward(indices) -> (extrinsics, intrinsics, depth, conf)`.
"""
from __future__ import annotations

import logging
import math
from typing import Callable

import numpy as np

log = logging.getLogger("roomdiff")


def plan_passes(n_before: int, n_after: int, capacity: int, anchors_per_video: int = 4):
    """Return (passes, anchors). Each pass is a sorted list of frame indices
    (before frames are 0..n_before-1, after frames follow)."""
    n = n_before + n_after
    if n <= capacity:
        return [list(range(n))], []
    apv = max(2, min(anchors_per_video, n_before, n_after))
    anchors = sorted(set(np.linspace(0, n_before - 1, apv).round().astype(int).tolist()) |
                     set((n_before + np.linspace(0, n_after - 1, apv).round().astype(int)).tolist()))
    room = capacity - len(anchors)
    if room < 4:
        raise ValueError(f"capacity {capacity} too small for {len(anchors)} anchors")
    rest_b = [i for i in range(n_before) if i not in anchors]
    rest_a = [i for i in range(n_before, n) if i not in anchors]
    n_pass = math.ceil((len(rest_b) + len(rest_a)) / room)
    while True:
        # interleave so every pass covers the whole room, not one corner
        passes = [sorted(anchors + rest_b[j::n_pass] + rest_a[j::n_pass]) for j in range(n_pass)]
        if max(len(p) for p in passes) <= capacity:
            return passes, anchors
        n_pass += 1


def _backproject(depth, K, T_wc, mask, stride=4):
    v, u = np.nonzero(mask[::stride, ::stride])
    v, u = v * stride, u * stride
    z = depth[v, u]
    x = (u + .5 - K[0, 2]) / K[0, 0] * z
    y = (v + .5 - K[1, 2]) / K[1, 1] * z
    pc = np.stack([x, y, z], 1)
    return pc @ T_wc[:3, :3].T + T_wc[:3, 3]


def umeyama(src: np.ndarray, dst: np.ndarray):
    """Similarity (s, R, t) minimising |s R src + t - dst|^2."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    cov = b.T @ a / len(src)
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    var = (a ** 2).sum() / len(src)
    s = float(np.trace(np.diag(S) @ D) / var)
    t = mu_d - s * R @ mu_s
    return s, R, t


def robust_umeyama(src, dst, iters: int = 4, keep: float = 0.8):
    sel = np.ones(len(src), bool)
    for _ in range(iters):
        s, R, t = umeyama(src[sel], dst[sel])
        r = np.linalg.norm(src @ (s * R).T + t - dst, axis=1)
        sel = r <= np.quantile(r, keep)
    s, R, t = umeyama(src[sel], dst[sel])
    r = np.linalg.norm(src @ (s * R).T + t - dst, axis=1)
    return s, R, t, float(np.median(r[sel])), float(np.median(np.linalg.norm(dst - dst.mean(0), axis=1)))


def _to_Twc(extr):
    T = np.eye(4)
    T[:3, :] = extr
    return np.linalg.inv(T)


def _rank01(conf, valid):
    flat = np.sort(conf[valid])
    # mid-rank, so ties (a flat confidence map) land at 0.5 instead of 0
    r = (np.searchsorted(flat, conf, "left") + np.searchsorted(flat, conf, "right")) / (2 * max(len(flat), 1))
    return np.where(valid, r, 0).astype(np.float32)


def stitched_forward(n_before: int, n_after: int, capacity: int, valid: np.ndarray,
                     forward: Callable, oom_errors: tuple = (), min_capacity: int = 12):
    """Run `forward` over all frames in as many passes as needed and return
    per-frame camera-to-world poses, intrinsics, depth and [0,1] confidence,
    all in the frame of the first pass. Shrinks the passes on out-of-memory."""
    n = n_before + n_after
    while True:
        passes, anchors = plan_passes(n_before, n_after, capacity)
        try:
            outs = []
            for j, sel in enumerate(passes):
                if len(passes) > 1:
                    log.info("VGGT pass %d/%d: %d frames (%d anchors)", j + 1, len(passes), len(sel), len(anchors))
                outs.append((sel, forward(np.array(sel))))
            break
        except oom_errors:
            if capacity <= min_capacity:
                raise
            capacity = max(min_capacity, int(capacity * 0.8))
            log.warning("out of GPU memory, retrying with at most %d frames per pass", capacity)

    T_wc = [None] * n
    K = [None] * n
    depth = [None] * n
    conf = [None] * n
    stats = []
    base_sel, (e0, k0, d0, c0) = outs[0]
    base = {idx: (_to_Twc(e0[i]), k0[i], d0[i], _rank01(c0[i], valid[idx])) for i, idx in enumerate(base_sel)}
    for idx, v in base.items():
        T_wc[idx], K[idx], depth[idx], conf[idx] = v

    for sel, (e, k, d, c) in outs[1:]:
        loc = {idx: i for i, idx in enumerate(sel)}
        src, dst = [], []
        for a in anchors:
            i = loc[a]
            Tj, T0 = _to_Twc(e[i]), base[a][0]
            cj, c0a = _rank01(c[i], valid[a]), base[a][3]
            m = valid[a] & (cj > 0.4) & (c0a > 0.4) & (d[i] > 0) & (base[a][2] > 0)
            src.append(_backproject(d[i], k[i], Tj, m))
            dst.append(_backproject(base[a][2], base[a][1], T0, m))
        src, dst = np.concatenate(src), np.concatenate(dst)
        s, R, t, resid, spread = robust_umeyama(src, dst)
        stats.append({"scale": s, "residual_rel": resid / max(spread, 1e-9)})
        log.info("  stitched pass: scale %.3f, anchor residual %.1f%% of scene size", s, 100 * resid / max(spread, 1e-9))
        S = np.eye(4)
        S[:3, :3], S[:3, 3] = s * R, t
        for i, idx in enumerate(sel):
            if T_wc[idx] is not None:
                continue
            Tj = _to_Twc(e[i])
            T = np.eye(4)
            T[:3, :3] = R @ Tj[:3, :3]
            T[:3, 3] = S[:3, :3] @ Tj[:3, 3] + t
            T_wc[idx], K[idx], depth[idx], conf[idx] = T, k[i], d[i] * s, _rank01(c[i], valid[idx])
    return np.stack(T_wc), np.stack(K), np.stack(depth), np.stack(conf), {
        "passes": len(passes), "frames_per_pass": capacity, "anchors": len(anchors), "stitch": stats}
