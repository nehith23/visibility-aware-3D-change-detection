"""Projection, point clouds, gravity, floor and metric scale."""
from __future__ import annotations

import logging
from dataclasses import replace

import numpy as np
from scipy.ndimage import maximum_filter, minimum_filter

from .scene import Frame, Scan

log = logging.getLogger("roomdiff")


# --------------------------------------------------------------------------
# basic projection
# --------------------------------------------------------------------------
def backproject(frame: Frame, stride: int = 1, flying_ratio: float = 0.0,
                mask: np.ndarray | None = None):
    """Return world points, colours and pixel coords for valid depth pixels."""
    H, W = frame.hw
    d = frame.depth
    ok = d > 0
    if frame.valid is not None:
        ok &= frame.valid
    if mask is not None:
        ok &= mask
    if flying_ratio > 0:
        # depth discontinuities produce "flying pixels" smeared between the
        # foreground and the background; drop them.
        dmax = maximum_filter(d, size=3)
        dmin = minimum_filter(np.where(d > 0, d, np.inf), size=3)
        ok &= (dmax - dmin) < flying_ratio * d
    sub = np.zeros_like(ok)
    sub[::stride, ::stride] = True
    ok &= sub
    v, u = np.nonzero(ok)
    z = d[v, u]
    K = frame.K
    x = (u + .5 - K[0, 2]) / K[0, 0] * z
    y = (v + .5 - K[1, 2]) / K[1, 1] * z
    pc = np.stack([x, y, z], 1)
    pw = pc @ frame.T_wc[:3, :3].T + frame.T_wc[:3, 3]
    return pw, frame.image[v, u], np.stack([u, v], 1)


def project(points: np.ndarray, frame: Frame):
    """World points -> (u, v) pixel coords and camera depth z."""
    T = frame.T_cw
    pc = points @ T[:3, :3].T + T[:3, 3]
    z = pc[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = frame.K[0, 0] * pc[:, 0] / z + frame.K[0, 2]
        v = frame.K[1, 1] * pc[:, 1] / z + frame.K[1, 2]
    return u, v, z


def voxel_downsample(points: np.ndarray, *attrs: np.ndarray, size: float):
    """Average points (and per-point attributes) inside each voxel."""
    if len(points) == 0:
        return (points, *attrs)
    keys = np.floor(points / size).astype(np.int64)
    _, inv, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    out = []
    for a in (points, *attrs):
        a2 = a.reshape(len(a), -1).astype(np.float64)
        acc = np.zeros((len(counts), a2.shape[1]))
        np.add.at(acc, inv, a2)
        acc /= counts[:, None]
        out.append(acc.reshape((len(counts),) + a.shape[1:]).astype(a.dtype if a.dtype.kind == "f" else np.float64))
    return tuple(out)


# --------------------------------------------------------------------------
# room frame: gravity, floor, scale
# --------------------------------------------------------------------------
def estimate_down(scans: list[Scan]) -> np.ndarray:
    """People hold phones upright, so the image 'down' axis of every frame,
    averaged over a whole recording, is a good first guess for gravity."""
    ys = np.concatenate([[f.T_wc[:3, 1] for f in s.frames] for s in scans])
    d = ys.mean(0)
    return d / np.linalg.norm(d)


def fit_floor(points: np.ndarray, down: np.ndarray, rng=None, iters: int = 400):
    """Find the floor: a large plane roughly perpendicular to gravity, at the
    low end of the height distribution. Returns (unit up normal, offset) with
    plane n.p + c = 0 and the inlier ratio."""
    rng = rng or np.random.default_rng(0)
    h = points @ down                                  # larger = lower
    lo, hi = np.percentile(h, [2, 99.5])
    extent = max(hi - lo, 1e-6)
    tol = 0.01 * extent
    # candidate floor points: the lowest slab of the scene
    cand = points[h > hi - 0.15 * extent]
    if len(cand) < 50:
        cand = points[h > np.percentile(h, 80)]
    best, best_inl = None, -1
    for _ in range(iters):
        p = cand[rng.choice(len(cand), 3, replace=False)]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn
        if abs(n @ down) < np.cos(np.deg2rad(25)):
            continue
        inl = np.abs((cand - p[0]) @ n) < tol
        cnt = inl.sum()
        if cnt > best_inl:
            best_inl, best = cnt, (n, p[0])
    if best is None:
        n = -down
        c = -(n @ points[h > np.percentile(h, 97)].mean(0))
        return n, c, 0.0
    n, p0 = best
    inl = cand[np.abs((cand - p0) @ n) < tol]
    centroid = inl.mean(0)
    _, _, vt = np.linalg.svd(inl - centroid, full_matrices=False)
    n = vt[-1]
    if n @ down > 0:
        n = -n                                         # point up
    c = -n @ centroid
    return n, c, best_inl / len(cand)


def to_room_frame(scans: list[Scan], camera_height: float = 1.35,
                  scale: float = 0.0, stride: int = 4):
    """Rotate/scale/translate both scans into the metric room frame."""
    pts = np.concatenate([backproject(f, stride)[0] for s in scans for f in s.frames])
    if len(pts) > 200_000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 200_000, replace=False)]
    down = estimate_down(scans)
    up, c, inlier_ratio = fit_floor(pts, down)

    cams = np.concatenate([s.camera_centers() for s in scans])
    cam_h = cams @ up + c
    if scale <= 0:
        med = np.median(cam_h)
        if med <= 0 or inlier_ratio < 0.05:
            log.warning("Floor not found reliably, metric scale will be off. "
                        "Pass --scale to fix it.")
            scale = 1.0 if med <= 0 else camera_height / med
        else:
            scale = camera_height / med

    # axes: z = up, y = first "before" camera's forward direction projected
    # onto the floor plane, x = y cross z.
    f0 = scans[0].frames[0].T_wc
    fwd = f0[:3, 2] - (f0[:3, 2] @ up) * up
    if np.linalg.norm(fwd) < 1e-6:
        fwd = f0[:3, 0] - (f0[:3, 0] @ up) * up
    y = fwd / np.linalg.norm(fwd)
    x = np.cross(y, up)
    R_rw = np.stack([x, y, up], 0)                     # world -> room rotation
    origin = f0[:3, 3] - (f0[:3, 3] @ up + c) * up      # foot of first camera

    def tf_pose(T):
        M = np.eye(4)
        M[:3, :3] = R_rw @ T[:3, :3]
        M[:3, 3] = scale * (R_rw @ (T[:3, 3] - origin))
        return M

    out = [Scan(s.name, [replace(f, T_wc=tf_pose(f.T_wc), depth=f.depth * scale)
                         for f in s.frames]) for s in scans]
    T_room_recon = np.eye(4)
    T_room_recon[:3, :3] = scale * R_rw
    T_room_recon[:3, 3] = -scale * R_rw @ origin
    info = {"scale": float(scale), "floor_inlier_ratio": float(inlier_ratio),
            "camera_height_spread": float(np.std(cam_h * scale)),
            "T_room_recon": T_room_recon}
    log.info("room frame: scale %.3f, floor inliers %.0f%%, camera height spread %.2f m",
             scale, 100 * inlier_ratio, info["camera_height_spread"])
    return out, info


# --------------------------------------------------------------------------
# robust depth lookups used by the visibility test
# --------------------------------------------------------------------------
def depth_windows(frame: Frame, conf_min: float, window: int):
    """Pre-compute min/max depth in a window around every pixel. Invalid or
    low-confidence pixels count as 0 so they can never vote "see-through"."""
    d = frame.depth.copy()
    bad = (d <= 0) | (frame.conf < conf_min)
    if frame.valid is not None:
        bad |= ~frame.valid
    d[bad] = 0
    dmin = minimum_filter(d, size=window)              # any invalid -> 0
    big = np.where(bad, -np.inf, d)
    dmax = maximum_filter(big, size=window)
    small = np.where(bad, np.inf, d)
    dmin_valid = minimum_filter(small, size=window)
    return d, dmin, dmax, dmin_valid


# --------------------------------------------------------------------------
# before/after alignment refinement
# --------------------------------------------------------------------------
def _normals(points: np.ndarray, k: int = 12) -> np.ndarray:
    from scipy.spatial import cKDTree
    _, idx = cKDTree(points).query(points, k=k)
    nb = points[idx] - points[idx].mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb)
    _, vec = np.linalg.eigh(cov)
    return vec[:, :, 0]


def icp(src: np.ndarray, tgt: np.ndarray, iters: int = 25, max_dist: float = 0.15,
        keep: float = 0.7, n_tgt: np.ndarray | None = None) -> np.ndarray:
    """Trimmed point-to-plane ICP; returns the 4x4 rigid transform src -> tgt."""
    from scipy.spatial import cKDTree
    if len(src) < 30 or len(tgt) < 30:
        return np.eye(4)
    n_tgt = _normals(tgt) if n_tgt is None else n_tgt
    tree = cKDTree(tgt)
    T = np.eye(4)
    cur = src.copy()
    for _ in range(iters):
        d, j = tree.query(cur, distance_upper_bound=max_dist)
        ok = np.isfinite(d)
        if ok.sum() < 20:
            break
        sel = ok & (d <= np.quantile(d[ok], keep))
        p, q, n = cur[sel], tgt[j[sel]], n_tgt[j[sel]]
        A = np.c_[np.cross(p, n), n]
        b = ((q - p) * n).sum(1)
        x, *_ = np.linalg.lstsq(A, b, rcond=None)
        a, t = x[:3], x[3:]
        R = np.array([[1, -a[2], a[1]], [a[2], 1, -a[0]], [-a[1], a[0], 1]])
        u, _, vt = np.linalg.svd(R)
        R = u @ vt
        step = np.eye(4)
        step[:3, :3], step[:3, 3] = R, t
        cur = cur @ R.T + t
        T = step @ T
        if np.linalg.norm(t) < 1e-4 and np.abs(a).max() < 1e-5:
            break
    return T


def refine_alignment(before: Scan, after: Scan, voxel: float = 0.03, iters: int = 30,
                     max_dist: float = 0.15, keep: float = 0.7):
    """Trimmed point-to-plane ICP of the 'after' cloud onto the 'before' cloud.

    The joint VGGT pass already puts both recordings in one frame, but a
    residual tilt of a degree or two is common, and it turns entire walls
    into false changes. Real changes are a small part of the room, so
    matching only the closest 70% of correspondences each iteration aligns
    on the static structure and ignores what moved."""
    from scipy.spatial import cKDTree

    def cloud(scan):
        pts = []
        for f in scan.frames:
            conf = f.conf >= np.percentile(f.conf, 30) if f.conf.std() > 0 else None
            m = f.depth < 4.5
            m = m if conf is None else (m & conf)
            pts.append(backproject(f, 4, 0.04, m)[0])
        p = np.concatenate(pts)
        return voxel_downsample(p, size=voxel)[0]

    tgt, src = cloud(before), cloud(after)
    if len(tgt) < 500 or len(src) < 500:
        return after, np.eye(4), {"icp": "skipped"}
    n_t = _normals(tgt)
    tree = cKDTree(tgt)
    T = np.eye(4)
    cur = src.copy()
    for it in range(iters):
        d, j = tree.query(cur, distance_upper_bound=max_dist)
        ok = np.isfinite(d)
        if ok.sum() < 300:
            break
        thr = np.quantile(d[ok], keep)
        sel = ok & (d <= thr)
        p, q, n = cur[sel], tgt[j[sel]], n_t[j[sel]]
        A = np.c_[np.cross(p, n), n]
        b = ((q - p) * n).sum(1)
        x, *_ = np.linalg.lstsq(A, b, rcond=None)
        a, t = x[:3], x[3:]
        R = np.array([[1, -a[2], a[1]], [a[2], 1, -a[0]], [-a[1], a[0], 1]])
        u, _, vt = np.linalg.svd(R)
        R = u @ vt
        step = np.eye(4)
        step[:3, :3], step[:3, 3] = R, t
        cur = cur @ R.T + t
        T = step @ T
        if np.linalg.norm(t) < 1e-4 and np.abs(a).max() < 1e-5:
            break
    # fit quality = share of 'after' points within 3 cm of the 'before' surface;
    # a median over all points is dominated by areas only one video saw
    tight = max(0.03, voxel)
    in_before = float((tree.query(src)[0] < tight).mean())
    in_after = float((tree.query(cur)[0] < tight).mean())
    ang = np.degrees(np.arccos(np.clip((np.trace(T[:3, :3]) - 1) / 2, -1, 1)))
    info = {"icp_rotation_deg": float(ang), "icp_translation_m": float(np.linalg.norm(T[:3, 3])),
            "icp_overlap_before": in_before, "icp_overlap_after": in_after,
            "icp_iterations": it + 1}
    # only accept a refinement that actually improves the fit and stays small
    if in_after < in_before * 1.01 or ang > 10 or np.linalg.norm(T[:3, 3]) > 0.5:
        log.info("alignment refinement rejected (%.1f deg, %.2f m)", ang, np.linalg.norm(T[:3, 3]))
        info["icp"] = "rejected"
        return after, np.eye(4), info
    log.info("alignment refined: %.2f deg, %.3f m; points within %.0f cm: %.0f%% -> %.0f%%",
             ang, np.linalg.norm(T[:3, 3]), 100 * tight, 100 * in_before, 100 * in_after)
    info["icp"] = "applied"
    return Scan(after.name, [replace(f, T_wc=T @ f.T_wc) for f in after.frames]), T, info
