"""Visibility-aware change detection.

The question we ask of every 3D point p from one recording is not "is there a
point near p in the other recording?" (which confuses *removed* with *never
looked at*), but "did the other recording's cameras see *through* p?".

For each camera of the other recording we project p and compare its depth z
with the depth the camera actually measured at that pixel, d:

    |d - z| < tol   -> consistent: the surface is still there
    d > z + tol     -> see-through: the camera saw space behind p, so p is gone
    d < z - tol     -> occluded: something is in front, no information
    off-screen      -> no information

Votes are pooled over all cameras, giving three states per point:
present, gone, or unobserved. Only "gone" points become change candidates and
"unobserved" points are reported as regions we could not verify.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.ndimage import maximum_filter, minimum_filter
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

from .config import Config
from .geometry import _normals, backproject, depth_windows, project, voxel_downsample
from .scene import Scan

log = logging.getLogger("roomdiff")

PRESENT, GONE, UNOBSERVED, AMBIGUOUS = 0, 1, 2, 3

# every candidate a filter drops, with the reason; reset by detect() and
# written to report.json so nothing disappears silently
REJECTED: list[dict] = []


def _reject(r: "Region", filt: str, detail: str = "") -> None:
    REJECTED.append({"scan": r.scan, "center": np.round(r.box_center, 2).tolist(),
                     "size_m": np.round(r.dims, 2).tolist(), "points": int(len(r.points)),
                     "filter": filt, "detail": detail})
    log.info("not reporting %s region at %s (%d points): %s%s", r.scan,
             np.round(r.box_center, 2).tolist(), len(r.points), filt, f" ({detail})" if detail else "")


# --------------------------------------------------------------------------
# point clouds
# --------------------------------------------------------------------------
def scan_cloud(scan: Scan, cfg: Config):
    pts, cols = [], []
    for f in scan.frames:
        conf_ok = f.conf >= np.percentile(f.conf, cfg.conf_drop_percentile) if f.conf.std() > 0 else None
        near = (f.depth < cfg.max_depth) if cfg.max_depth > 0 else None
        mask = conf_ok if near is None else (near if conf_ok is None else conf_ok & near)
        p, c, _ = backproject(f, cfg.pixel_stride, cfg.flying_pixel_ratio, mask)
        pts.append(p)
        cols.append(c)
    pts, cols = np.concatenate(pts), np.concatenate(cols).astype(np.float32)
    pts, cols = voxel_downsample(pts, cols, size=cfg.voxel)
    return pts.astype(np.float32), cols.astype(np.float32)


class DepthIndex:
    """Pre-filtered depth maps of one scan, ready for fast visibility queries."""

    def __init__(self, scan: Scan, cfg: Config):
        self.frames = scan.frames
        self.maps = []
        for f in scan.frames:
            conf_min = np.percentile(f.conf, cfg.conf_drop_percentile) if f.conf.std() > 0 else 0
            self.maps.append(depth_windows(f, conf_min, cfg.window))
        self.cfg = cfg

    def votes(self, pts: np.ndarray, normals: np.ndarray | None = None):
        """Per point: number of frames that agree, that see through it, and
        per-frame boolean masks (used later to pick evidence views).

        With surface normals the depth tolerance grows as 1/cos of the angle
        between the viewing ray and the surface (capped). A floor seen at a
        grazing angle down a corridor turns a 2 cm height error into ~9 cm of
        depth along the ray; without this it reads as 'seen through'."""
        cfg = self.cfg
        n = len(pts)
        agree = np.zeros(n, np.int32)
        through = np.zeros(n, np.int32)
        agree_masks, through_masks = [], []
        for f, (d, dmin, dmax, dmin_valid) in zip(self.frames, self.maps):
            H, W = f.hw
            u, v, z = project(pts, f)
            ok = (z > 0.05) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            ui = np.clip(u, 0, W - 1).astype(int)
            vi = np.clip(v, 0, H - 1).astype(int)
            tol = np.maximum(cfg.depth_tol_abs, cfg.depth_tol_rel * z)
            if normals is not None:
                ray = pts - f.center
                cos = np.abs((ray * normals).sum(1)) / np.maximum(np.linalg.norm(ray, axis=1), 1e-9)
                # horizontal surfaces (floor, table tops) seen at grazing
                # angles get the full allowance; walls and object sides less
                cap = np.where(np.abs(normals[:, 2]) > 0.9, cfg.grazing_min_cos_floor, cfg.grazing_min_cos)
                tol = tol / np.maximum(cos, cap)
            dc, dn, dx, dnv = d[vi, ui], dmin[vi, ui], dmax[vi, ui], dmin_valid[vi, ui]
            a = ok & (((dc > 0) & (np.abs(dc - z) < tol)) | ((dnv <= z + tol) & (dx >= z - tol)))
            t = ok & ~a & (dn > z + tol)               # every neighbour is behind p
            agree += a
            through += t
            agree_masks.append(a)
            through_masks.append(t)
        return agree, through, agree_masks, through_masks


def classify(agree: np.ndarray, through: np.ndarray, cfg: Config) -> np.ndarray:
    evidence = agree + through
    state = np.full(len(agree), AMBIGUOUS, np.int8)
    ratio = np.divide(through, np.maximum(evidence, 1))
    state[(through >= cfg.min_votes) & (ratio >= cfg.vanish_ratio)] = GONE
    state[(agree >= 1) & (state != GONE)] = PRESENT
    state[evidence == 0] = UNOBSERVED
    return state


# --------------------------------------------------------------------------
# objects
# --------------------------------------------------------------------------
@dataclass(eq=False)          # identity comparison; fields hold numpy arrays
class Region:
    """A cluster of points that vanished from one recording."""
    scan: str                   # recording the points belong to
    points: np.ndarray
    colors: np.ndarray
    center: np.ndarray = field(init=False)
    box_center: np.ndarray = field(init=False)
    dims: np.ndarray = field(init=False)      # (length, width, height) metres
    yaw: float = field(init=False)            # degrees, footprint orientation
    corners: np.ndarray = field(init=False)   # (8, 3)
    embedding: np.ndarray | None = None
    normals: np.ndarray | None = None
    label: str = "object"
    label_score: float = 0.0
    color_name: str = ""
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        p = self.points
        self.center = p.mean(0)
        rect = cv2.minAreaRect(p[:, :2].astype(np.float32))
        (cx, cy), (w, l), ang = rect
        z0, z1 = np.percentile(p[:, 2], [1, 99])
        z0 = max(z0 - 0.01, 0.0) if z0 < 0.06 else z0   # snap to floor
        self.box_center = np.array([cx, cy, (z0 + z1) / 2])
        self.dims = np.array([max(w, l), min(w, l), max(z1 - z0, 0.02)])
        self.yaw = float(ang if w >= l else ang + 90)
        box2 = cv2.boxPoints(rect)
        self.corners = np.array([[x, y, z] for z in (z0, z1) for x, y in box2])

    def set_bottom(self, z0: float) -> None:
        z1 = self.top
        self.corners[:4, 2] = z0
        self.box_center[2] = (z0 + z1) / 2
        self.dims[2] = max(z1 - z0, 0.02)

    def footprint_mask(self, pts: np.ndarray, margin: float = 0.0) -> np.ndarray:
        """Points whose xy falls inside the (optionally grown) footprint."""
        c = self.box_center[:2]
        t = np.deg2rad(self.yaw)
        R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
        loc = (pts[:, :2] - c) @ R.T
        half = np.array([self.dims[0], self.dims[1]]) / 2 + margin
        return (np.abs(loc[:, 0]) <= half[0]) & (np.abs(loc[:, 1]) <= half[1])

    @property
    def bottom(self) -> float:
        return float(self.corners[:, 2].min())

    @property
    def top(self) -> float:
        return float(self.corners[:, 2].max())


@dataclass(eq=False)          # identity comparison; fields hold numpy arrays
class Change:
    kind: str                         # moved / added / removed
    region: Region                    # where it is in its own recording
    target: Region | None = None      # for moved: where it ended up
    displacement: np.ndarray | None = None
    rotation: float | None = None
    confidence: float = 1.0
    description: str = ""
    id: int = 0
    confident: bool = True


def cluster_regions(pts, cols, mask, scan_name, cfg: Config, nrm=None) -> list[Region]:
    idx = np.nonzero(mask)[0]
    if len(idx) < cfg.min_cluster_points:
        return []
    labels = DBSCAN(eps=cfg.cluster_eps, min_samples=cfg.cluster_min_samples).fit_predict(pts[idx])
    labels = _merge_close(pts[idx], labels, cfg.merge_gap)
    regions = []
    for lab in set(labels) - {-1}:
        sel = idx[labels == lab]
        if len(sel) < cfg.min_cluster_points:
            continue
        r = Region(scan_name, pts[sel], cols[sel])
        r.normals = None if nrm is None else nrm[sel]
        if r.dims.max() < cfg.min_cluster_extent:
            _reject(r, "smaller than the minimum object extent")
            continue
        # large, paper-thin sheets are almost always registration error on a
        # wall or floor, not a real object.
        if r.dims[0] * r.dims[1] > cfg.max_sheet_area and min(r.dims) < 0.04:
            _reject(r, "large paper-thin sheet (misalignment)")
            continue
        if r.dims[2] < 0.03 and r.top < 0.05:
            _reject(r, "floor-level smear")
            continue
        sp = np.sqrt(np.clip(np.sort(np.linalg.eigvalsh(np.cov(r.points.T)))[::-1], 0, None))
        if sp[0] * sp[1] > cfg.sheet_min_extent and (sp[2] < cfg.sheet_max_thickness
                                                     or sp[2] < cfg.sheet_max_flatness * sp[1]):
            # a big planar slice of wall or carpet: the surface itself is still
            # there, it was just reconstructed a few cm off in one recording
            _reject(r, "planar slice of wall or floor (misregistration)")
            continue
        if _is_thin(r, cfg):
            continue
        regions.append(r)
    return regions


def _is_thin(r: "Region", cfg: Config) -> bool:
    """Bicycle tubes, lock cables, chair legs and seat posts are 1 to 4 cm
    thick: at 518 px their depth flickers between the object and whatever is
    behind it, so they look 'seen through' from some views. They are below
    the depth resolution of this pipeline, so they are not reported."""
    ev = np.sort(np.linalg.eigvalsh(np.cov(r.points.T)))[::-1]
    if np.sqrt(max(ev[1], 0)) < cfg.line_max_spread:
        _reject(r, "line-like (tube or cable, below depth resolution)")
        return True
    if r.dims[1] < cfg.pole_max_width and r.dims[2] > cfg.pole_aspect * r.dims[0]:
        _reject(r, "pole-like (below depth resolution)")
        return True
    return False


def region_confidence(r: "Region") -> float:
    """0..1 from the region's own evidence: size (log-scaled, 120 points to
    2000), how different the scene looks where it was seen through, how
    compact it is rather than edge-like, how much of it survives local
    re-registration, how many independent views saw through it, and whether
    it is a thin slab (a door leaf or a slice of wall)."""
    ev = r.evidence
    size = float(np.clip(np.log(max(len(r.points), 1) / 120) / np.log(2000 / 120), 0, 1))
    # evidence from a single pair of frames is weak: full weight from 4 views
    views = float(np.clip((ev.get("see_through_views", 4) - 1) / 3, 0, 1))
    # door leaves and wall slices are thin slabs; real objects are deeper
    thick = float(np.sqrt(np.clip(min(r.dims[0], r.dims[1]) / 0.10, 0, 1)))
    look = float(ev.get("appearance_changed", 1.0))
    compact = 1 - float(np.clip(ev.get("edge_excess", 0.0) / 0.25, 0, 1))
    local = float(ev.get("local_recheck", {}).get("still_gone", 1.0))
    return float(np.sqrt(size) * look * (0.5 + 0.5 * compact) * local * views * thick)


def _significant(r: "Region", cfg: Config) -> bool:
    """Big regions pass on size. Small ones (a bottle on a desk) must clear a
    higher bar: the scene clearly looks different there, the region is
    compact rather than edge-like, and it survives local re-registration."""
    n = len(r.points)
    if n >= cfg.min_report_points:
        return True
    ev = r.evidence
    ok = (n >= cfg.min_cluster_points and ev.get("appearance_changed", 0) >= 0.85
          and ev.get("edge_excess", 1) <= 0.10 and ev.get("local_recheck", {}).get("still_gone", 1) >= 0.9)
    if not ok:
        _reject(r, "small and evidence not strong enough")
    return ok


def _merge_close(pts: np.ndarray, labels: np.ndarray, gap: float) -> np.ndarray:
    """Attach small fragments to a much larger cluster close by: depth noise
    can split one object (a chair's backrest top from its seat). Strictly
    one-way: a fragment joins its nearest host, hosts never merge with each
    other, so separate objects (a backpack next to a bike) cannot chain into
    one blob."""
    ids = [l for l in set(labels) if l != -1]
    if len(ids) < 2 or gap <= 0:
        return labels
    size = {l: int((labels == l).sum()) for l in ids}
    hosts = [l for l in ids if size[l] >= 150]
    trees = {l: cKDTree(pts[labels == l]) for l in hosts}
    out = labels.copy()
    for f in ids:
        if f in hosts:
            continue
        pf = pts[labels == f]
        best, best_d = None, 2 * gap
        for h in hosts:
            if size[h] < 4 * size[f]:
                continue
            d = trees[h].query(pf, distance_upper_bound=best_d)[0].min()
            if d < best_d:
                best, best_d = h, d
        if best is not None:
            out[labels == f] = best
    return out


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.reshape(1, -1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(float)


def _yaw_and_fit(src: Region, dst: Region):
    """Brute force yaw search aligning the footprints of two regions."""
    a = src.points - np.r_[src.box_center[:2], 0]
    b = dst.points - np.r_[dst.box_center[:2], 0]
    tb, ta = cKDTree(b), cKDTree(a)

    def score(yaw):
        t = np.deg2rad(yaw)
        R = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
        # symmetric chamfer: both clouds are partial views, one-way distances
        # would reward rotating the smaller one into the bigger one
        return np.median(tb.query(a @ R.T)[0]) + np.median(ta.query(b @ R)[0])

    scores = {y: score(y) for y in range(0, 360, 5)}
    coarse = min(scores, key=scores.get)
    fine = {y: score(y) for y in np.arange(coarse - 4, coarse + 5, 1.0)}
    best_yaw = min(fine, key=fine.get)
    best = fine[best_yaw]
    yaw = ((best_yaw + 180) % 360) - 180
    # only report rotation if it clearly beats "no rotation"
    if scores[0] > 0 and best > 0.75 * scores[0] and abs(yaw) > 0:
        yaw_reported = None
    else:
        yaw_reported = float(yaw)
    return yaw_reported, float(best)


def match_moves(removed: list[Region], added: list[Region], cfg: Config):
    """Pair regions that vanished from 'before' with regions that appeared in
    'after' when they look like the same object."""
    if not removed or not added:
        return [], removed, added
    C = np.zeros((len(removed), len(added)))
    for i, r in enumerate(removed):
        lab_r = _lab(r.colors).mean(0)
        for j, a in enumerate(added):
            ratio = np.abs(np.log(np.sort(r.dims) / np.sort(a.dims)))
            geo = np.mean(ratio)
            dcol = np.linalg.norm(lab_r - _lab(a.colors).mean(0))
            col = dcol / 40.0
            # hard plausibility gates: a moved object keeps its size and colour,
            # and fragments are never paired (they were behind the bogus
            # "wall sliver moved 3 m onto the desk" matches on real data)
            if (ratio.max() > np.log(cfg.move_max_size_ratio) or dcol > cfg.move_max_color
                    or min(len(r.points), len(a.points)) < cfg.move_min_points):
                C[i, j] = 1e6
                continue
            sem = 0.0
            if r.embedding is not None and a.embedding is not None:
                sem = 1.0 - float(r.embedding @ a.embedding)
                sem *= 2.0
            hgt = abs(r.bottom - a.bottom) / 0.5   # similar support height helps a little
            C[i, j] = 0.45 * geo + 0.35 * col + 0.35 * sem + 0.1 * min(hgt, 1)
    rows, cols = linear_sum_assignment(C)
    moves, used_r, used_a = [], set(), set()
    for i, j in zip(rows, cols):
        if C[i, j] > cfg.match_cost:
            continue
        r, a = removed[i], added[j]
        yaw, _ = _yaw_and_fit(r, a)
        disp = a.box_center - r.box_center
        disp[2] = a.bottom - r.bottom
        moves.append(Change("moved", r, a, disp, yaw, confidence=float(np.clip(1 - C[i, j] / cfg.match_cost, 0.05, 1))))
        used_r.add(i)
        used_a.add(j)
    return (moves,
            [r for k, r in enumerate(removed) if k not in used_r],
            [a for k, a in enumerate(added) if k not in used_a])


# --------------------------------------------------------------------------
# full detection
# --------------------------------------------------------------------------
@dataclass(eq=False)          # identity comparison; fields hold numpy arrays
class DetectionResult:
    clouds: dict                      # name -> (pts, cols)
    states: dict                      # name -> per point state vs other scan
    support: dict                     # name -> self support count
    removed: list
    added: list
    changes: list
    stats: dict


def detect(before: Scan, after: Scan, cfg: Config) -> DetectionResult:
    REJECTED.clear()
    clouds, states, support, regions = {}, {}, {}, {}
    idx = {s.name: DepthIndex(s, cfg) for s in (before, after)}
    stats = {}
    for me, other in ((before, after), (after, before)):
        pts, cols = scan_cloud(me, cfg)
        nrm = _normals(pts) if cfg.grazing_min_cos < 1 else None
        # self-consistency: a point must be seen by several frames of its own
        # recording, which removes flying pixels and transient junk.
        own_agree, _, _, _ = idx[me.name].votes(pts, nrm)
        keep = own_agree >= cfg.min_self_support
        pts, cols, own_agree = pts[keep], cols[keep], own_agree[keep]
        nrm = None if nrm is None else nrm[keep]
        agree, through, _, _ = idx[other.name].votes(pts, nrm)
        st = classify(agree, through, cfg)
        # the floor itself cannot be removed, and seen at a grazing angle
        # down a corridor it is the noisiest surface there is; objects on
        # it are found from their parts above this band
        st[(st == GONE) & (pts[:, 2] < cfg.floor_band)] = AMBIGUOUS
        clouds[me.name], states[me.name], support[me.name] = (pts, cols), st, own_agree
        n = len(st)
        stats[me.name] = {
            "points": int(n),
            "present": float((st == PRESENT).mean()),
            "gone": float((st == GONE).mean()),
            "unobserved": float((st == UNOBSERVED).mean()),
            "ambiguous": float((st == AMBIGUOUS).mean()),
        }
        regions[me.name] = cluster_regions(pts, cols, st == GONE, me.name, cfg, nrm)
        log.info("%s: %d points, %.1f%% gone, %.1f%% unobserved, %d candidate regions",
                 me.name, n, 100 * stats[me.name]["gone"], 100 * stats[me.name]["unobserved"],
                 len(regions[me.name]))
    for me, other in ((before, after), (after, before)):
        regions[me.name] = local_recheck(regions[me.name], clouds[me.name][0], clouds[other.name][0],
                                         idx[other.name], cfg)
        regions[me.name] = appearance_check(regions[me.name], other, idx[other.name], cfg)
        regions[me.name] = edge_check(regions[me.name], me, idx[me.name], cfg)
    return DetectionResult(clouds, states, support, regions[before.name], regions[after.name], [], stats)


def local_recheck(regions: list[Region], own_pts: np.ndarray, other_pts: np.ndarray,
                  other_index: "DepthIndex", cfg: Config) -> list[Region]:
    """Local re-registration test. Learned depth is not perfectly rigid
    across a room: one end can sit a few centimetres off between the two
    reconstructions even when the global alignment is right, and clutter
    there then looks 'seen through'. For each candidate, align only its
    surroundings (the candidate itself excluded) between the two scans with
    ICP, move the candidate along, and test it again. A real change survives
    (the bed is still there, the backpack is still gone); a distortion
    artefact does not."""
    from .geometry import icp
    kept = []
    tree_own, tree_other = cKDTree(own_pts), cKDTree(other_pts)
    for r in regions:
        c = r.box_center
        nb_own = own_pts[tree_own.query_ball_point(c, cfg.local_radius)]
        nb_other = other_pts[tree_other.query_ball_point(c, cfg.local_radius)]
        if len(nb_own) < 200 or len(nb_other) < 200:
            kept.append(r)
            continue
        # exclude the candidate (and a margin) so it cannot pull the fit
        far = cKDTree(r.points).query(nb_own)[0] > 0.05
        T = icp(nb_own[far], nb_other, max_dist=0.10)
        ang = np.degrees(np.arccos(np.clip((np.trace(T[:3, :3]) - 1) / 2, -1, 1)))
        if np.linalg.norm(T[:3, 3]) > 0.08 or ang > 4:
            kept.append(r)          # local fit unreliable (e.g. the region IS the neighbourhood)
            continue
        moved = r.points @ T[:3, :3].T + T[:3, 3]
        agree, through, _, _ = other_index.votes(moved, None if r.normals is None else r.normals @ T[:3, :3].T)
        gone = classify(agree, through, cfg) == GONE
        share = float(gone.mean())
        shift = float(np.linalg.norm(T[:3, 3]))
        r.evidence["local_recheck"] = {"still_gone": share, "local_shift_m": shift}
        if share >= cfg.local_keep_gone:
            kept.append(r)
        else:
            _reject(r, "vanishes after local re-registration",
                    f"only {100 * share:.0f}% still changed, shift {100 * shift:.1f} cm")
    return kept


def edge_check(regions: list[Region], own: Scan, own_index: "DepthIndex", cfg: Config) -> list[Region]:
    """See-through structures. A slatted bed footboard, bicycle spokes and
    tubes, cables and a 3D-printer frame put a depth discontinuity every few
    pixels; learned depth smears across them, and two recordings viewing
    them from opposite sides disagree everywhere. Measured on the null test
    (two videos of the unchanged room) these were all the large false
    positives, with 45-80% of their observations on depth edges, while the
    removed backpack sat at 20%. So a region seen mostly on depth edges is
    not trusted."""
    if not regions:
        return regions
    edges = []
    for f in own.frames:
        d = f.depth
        good = d > 0
        dmax = maximum_filter(np.where(good, d, 0), size=7)
        dmin = minimum_filter(np.where(good, d, np.inf), size=7)
        edges.append((dmax - dmin) / np.maximum(d, 1e-3) > 0.10)
    kept = []
    for r in regions:
        agree, _, masks, _ = own_index.votes(r.points, r.normals)
        on = tot = 0
        expected = []
        for f, m, E in zip(own.frames, masks, edges):
            if m.sum() < 3:
                continue
            u, v, _ = project(r.points[m], f)
            H, W = f.hw
            e = E[np.clip(v, 0, H - 1).astype(int), np.clip(u, 0, W - 1).astype(int)]
            on += int(e.sum())
            tot += len(e)
            # a compact object of apparent size s px has ~1-((s-6)/s)^2 of
            # its pixels inside the 7 px edge band around its own outline
            s = max(np.sqrt(max(np.ptp(u), 1) * max(np.ptp(v), 1)), 7.0)
            expected.append((1 - ((s - 6) / s) ** 2, len(e)))
        share = on / max(tot, 1)
        exp = sum(a * n for a, n in expected) / max(sum(n for _, n in expected), 1)
        excess = share - exp
        r.evidence["edge_share"], r.evidence["edge_excess"] = share, excess
        if excess <= cfg.edge_max_excess:
            kept.append(r)
        else:
            _reject(r, "see-through structure (slats, spokes, cables)",
                    f"{100 * share:.0f}% of observations on depth edges, {100 * exp:.0f}% expected for a solid object")
    return kept


def appearance_check(regions: list[Region], other: Scan, other_index: "DepthIndex",
                     cfg: Config) -> list[Region]:
    """Geometric evidence must be corroborated by appearance. When the other
    recording 'sees through' a removed backpack, the pixel it actually sees
    is the duvet behind it, which looks nothing like the backpack. When it
    'sees through' desk clutter whose depth is merely off, the pixel it sees
    is the same clutter. So for every see-through observation, compare the
    region's own colour with what the other camera saw at that pixel; keep
    the region only if the scene really looks different there."""
    kept = []
    for r in regions:
        _, _, _, through = other_index.votes(r.points, r.normals)
        # independent views that saw through the region: one or two frames
        # glancing past a far-away surface is how misregistration looks
        r.evidence["see_through_views"] = int(sum(int(m.sum()) >= 3 for m in through))
        own = _lab(r.colors)
        dists = []
        for f, m in zip(other.frames, through):
            if not m.any():
                continue
            u, v, _ = project(r.points[m], f)
            H, W = f.hw
            ui = np.clip(u, 0, W - 1).astype(int)
            vi = np.clip(v, 0, H - 1).astype(int)
            seen = _lab(f.image[vi, ui].astype(np.float32))
            dists.append(np.linalg.norm(own[m] - seen, axis=1))
        if not dists:
            kept.append(r)
            continue
        d = np.concatenate(dists)
        changed = float((d > cfg.appearance_delta_e).mean())
        r.evidence["appearance_changed"] = changed
        if changed >= cfg.appearance_min_changed:
            kept.append(r)
        else:
            _reject(r, "looks the same in the other recording",
                    f"only {100 * changed:.0f}% of the see-through views look different")
    return kept


def refine_support(r: Region, other_pts: np.ndarray) -> None:
    """The lowest few centimetres of an object rarely register as changed: the
    surface it stood on is within depth tolerance. Look at the *other*
    recording, where the object is absent, to find the surface underneath and
    extend the box down to it."""
    small = min(r.dims[:2]) < 0.2
    m = r.footprint_mask(other_pts, 0.03 if small else -0.02) & (other_pts[:, 2] < r.bottom + 0.03)
    if m.sum() < (3 if small else 10):
        if r.bottom < 0.15:
            r.set_bottom(0.0)
        return
    support = float(np.percentile(other_pts[m, 2], 90))
    if support < r.bottom:
        r.set_bottom(max(support, 0.0) if support > 0.04 else 0.0)


def assemble(res: DetectionResult, cfg: Config) -> list[Change]:
    for r in res.removed:
        refine_support(r, res.clouds["after"][0])
    for r in res.added:
        refine_support(r, res.clouds["before"][0])
    # a box extended down to its support can only now reveal a pole shape
    def keep(r):
        if _is_thin(r, cfg) or not _significant(r, cfg):
            return False
        if r.top < cfg.min_height:
            _reject(r, "too low (mat or paper on the floor)", f"top at {100 * r.top:.0f} cm")
            return False
        return True
    res.removed = [r for r in res.removed if keep(r)]
    res.added = [r for r in res.added if keep(r)]
    moves, removed, added = match_moves(res.removed, res.added, cfg)
    changes = moves + [Change("removed", r) for r in removed] + [Change("added", a) for a in added]
    for c in changes:
        conf = region_confidence(c.region)
        if c.target is not None:
            # a move is two independent detections of a matching object, one
            # where it was and one where it is: they corroborate each other
            both = 1 - (1 - conf) * (1 - region_confidence(c.target))
            conf = both * (0.6 + 0.4 * c.confidence)
        c.confidence = float(conf)
        c.confident = conf >= cfg.confident_score
    # confident changes first, then by confidence
    changes.sort(key=lambda c: (not c.confident, -c.confidence))
    for i, c in enumerate(changes, 1):
        c.id = i
    res.changes = changes
    return changes
