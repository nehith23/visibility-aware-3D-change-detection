"""A tiny ray-cast room with known changes, used for testing and the demo.

It renders RGB + depth for two camera paths and then hides the true scale and
orientation behind a random similarity transform, so the output looks like a
feed-forward reconstruction (first camera at the origin, unknown scale, no
gravity). The rest of the pipeline has to recover everything on its own.

Ground truth changes:
  * red chair      moved ~1.6 m and turned 90 degrees
  * cardboard box  removed
  * blue backpack  added on the floor
  * white bottle   added on the table
  * green bin      unchanged, but only "before" ever looks at it
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from ..scene import Frame, Scan


@dataclass
class Box:
    name: str
    center: tuple
    half: tuple
    color: tuple
    yaw: float = 0.0          # degrees about +z
    texture: float = 0.06     # strength of procedural texture


ROOM = (5.0, 4.0, 2.6)


def _structure() -> list[Box]:
    W, D, H = ROOM
    t = 0.05
    return [
        Box("floor", (W / 2, D / 2, -t), (W / 2 + .1, D / 2 + .1, t), (150, 120, 90), texture=.18),
        Box("ceiling", (W / 2, D / 2, H + t), (W / 2 + .1, D / 2 + .1, t), (235, 235, 230)),
        Box("wall", (W / 2, -t, H / 2), (W / 2 + .1, t, H / 2), (205, 210, 200), texture=.08),
        Box("wall", (W / 2, D + t, H / 2), (W / 2 + .1, t, H / 2), (200, 205, 215), texture=.08),
        Box("wall", (-t, D / 2, H / 2), (t, D / 2 + .1, H / 2), (210, 200, 195), texture=.08),
        Box("wall", (W + t, D / 2, H / 2), (t, D / 2 + .1, H / 2), (205, 205, 205), texture=.08),
        Box("door", (2.5, 4.0 - .01, 1.0), (.45, .02, 1.0), (120, 90, 60)),
        Box("rug", (3.0, 1.7, 0.005), (0.9, 0.6, 0.005), (90, 70, 110), texture=.25),
    ]


def scene_before() -> list[Box]:
    return _structure() + [
        Box("table", (3.5, 2.8, .375), (.6, .35, .375), (110, 75, 45)),
        Box("laptop", (3.3, 2.8, .77), (.16, .11, .02), (60, 60, 65)),
        Box("bookshelf", (4.8, 1.0, .9), (.18, .5, .9), (80, 55, 35), texture=.15),
        # chair = seat + backrest, so a 90 degree turn is actually observable
        Box("chair", (2.1, 1.6, .23), (.22, .22, .23), (190, 40, 40)),
        Box("chair", (2.1, 1.8, .67), (.22, .04, .21), (170, 35, 35)),
        Box("cardboard box", (1.0, 1.7, .16), (.22, .16, .16), (190, 150, 100)),
        Box("bin", (0.35, 3.6, .2), (.15, .15, .2), (40, 140, 60)),
        Box("lamp", (4.6, 3.6, .7), (.12, .12, .7), (230, 200, 120)),
    ]


CHAIR_FROM, CHAIR_TO, CHAIR_TURN = np.array([2.1, 1.6]), np.array([1.3, 2.65]), 90.0


def scene_after() -> list[Box]:
    objs = []
    for b in scene_before():
        if b.name == "cardboard box":
            continue                                   # removed
        if b.name == "chair":                          # moved + turned
            off = _rotz(CHAIR_TURN)[:2, :2] @ (np.asarray(b.center[:2]) - CHAIR_FROM)
            c = CHAIR_TO + off
            b = replace(b, center=(c[0], c[1], b.center[2]), yaw=b.yaw + CHAIR_TURN)
        objs.append(b)
    objs += [
        Box("backpack", (2.8, 2.0, .24), (.16, .11, .24), (40, 70, 170)),
        Box("bottle", (3.75, 2.65, .87), (.04, .04, .12), (235, 235, 240)),
    ]
    return objs


GROUND_TRUTH = [
    {"type": "moved", "name": "chair", "from": (2.1, 1.6, .45), "to": (1.3, 2.65, .45), "turn": 90.0},
    {"type": "removed", "name": "cardboard box", "at": (1.0, 1.7, .16)},
    {"type": "added", "name": "backpack", "at": (2.8, 2.0, .24)},
    {"type": "added", "name": "bottle", "at": (3.75, 2.65, .87)},
]
UNOBSERVED_UNCHANGED = [{"name": "bin", "at": (0.35, 3.6, .2)}]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _rotz(deg: float) -> np.ndarray:
    a = np.deg2rad(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def look_at(pos, target) -> np.ndarray:
    pos, target = np.asarray(pos, float), np.asarray(target, float)
    z = target - pos
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    T = np.eye(4)
    T[:3, :3] = np.stack([x, y, z], 1)
    T[:3, 3] = pos
    return T


def _hash_noise(p: np.ndarray, scale: float) -> np.ndarray:
    q = np.floor(p / scale)
    h = np.sin(q[:, 0] * 12.9898 + q[:, 1] * 78.233 + q[:, 2] * 37.719) * 43758.5453
    return h - np.floor(h)


def render(boxes: list[Box], T_wc: np.ndarray, K: np.ndarray, w: int, h: int):
    u, v = np.meshgrid(np.arange(w) + .5, np.arange(h) + .5)
    d_cam = np.stack([(u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1], np.ones_like(u)], -1).reshape(-1, 3)
    R, o = T_wc[:3, :3], T_wc[:3, 3]
    d_w = d_cam @ R.T                     # z_cam = 1, so ray t equals depth
    n_rays = len(d_w)
    best_t = np.full(n_rays, np.inf)
    best_i = np.full(n_rays, -1)
    best_n = np.zeros((n_rays, 3))
    for i, b in enumerate(boxes):
        Rb = _rotz(b.yaw)
        ol = Rb.T @ (o - np.asarray(b.center))
        dl = d_w @ Rb                      # == (Rb.T @ d.T).T
        hl = np.asarray(b.half)
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (-hl - ol) / dl
            t2 = (hl - ol) / dl
        tlo, thi = np.minimum(t1, t2), np.maximum(t1, t2)
        tmin, tmax = tlo.max(1), thi.min(1)
        axis = tlo.argmax(1)
        hit = (tmax >= tmin) & (tmin > 1e-3) & (tmin < best_t)
        best_t[hit], best_i[hit] = tmin[hit], i
        nl = np.zeros((hit.sum(), 3))
        nl[np.arange(hit.sum()), axis[hit]] = -np.sign(dl[hit, axis[hit]])
        best_n[hit] = nl @ Rb.T
    depth = np.where(np.isfinite(best_t), best_t, 0).reshape(h, w)
    pts = o + d_w * best_t[:, None]
    light = np.array([.3, -.5, .8]) / np.linalg.norm([.3, -.5, .8])
    shade = .55 + .45 * np.abs(best_n @ light)
    rgb = np.zeros((n_rays, 3))
    for i, b in enumerate(boxes):
        m = best_i == i
        if not m.any():
            continue
        tex = 1 + b.texture * (2 * _hash_noise(pts[m], .07) - 1) + b.texture * .5 * (2 * _hash_noise(pts[m], .013) - 1)
        rgb[m] = np.asarray(b.color) * (shade[m] * tex)[:, None]
    return np.clip(rgb, 0, 255).astype(np.uint8).reshape(h, w, 3), depth.astype(np.float32)


def _path_before(n):
    s = np.linspace(0, 1, n)
    pos = np.stack([0.7 + 3.4 * s, 0.35 + 0.25 * np.sin(np.pi * s), np.full(n, 1.35)], 1)
    tgt = np.stack([np.interp(s, [0, .3, .7, 1], [0.4, 1.6, 3.4, 4.6]),
                    np.interp(s, [0, .3, .7, 1], [3.4, 2.6, 2.6, 2.4]),
                    np.interp(s, [0, .5, 1], [0.35, 0.35, 0.6])], 1)
    return pos, tgt


def _path_after(n):
    s = np.linspace(0, 1, n)
    pos = np.stack([4.3 - 2.4 * s, 3.5 - 0.15 * np.sin(np.pi * s), np.full(n, 1.35)], 1)
    tgt = np.stack([np.interp(s, [0, .5, 1], [4.4, 2.6, 1.0]),
                    np.interp(s, [0, .5, 1], [1.0, 1.3, 1.6]),
                    np.full(n, 0.4)], 1)
    return pos, tgt


def generate(out_dir: str | Path, n_frames: int = 28, w: int = 320, h: int = 240,
             seed: int = 0) -> tuple[list[Scan], dict]:
    """Render both recordings. Returns scans in an arbitrary similarity frame
    plus the transform needed to map true room coordinates into that frame."""
    rng = np.random.default_rng(seed)
    out_dir = Path(out_dir)
    K = np.array([[260.0, 0, w / 2], [0, 260.0, h / 2], [0, 0, 1]])
    scans_true = []
    for name, boxes, path in [("before", scene_before(), _path_before),
                              ("after", scene_after(), _path_after)]:
        pos, tgt = path(n_frames)
        (out_dir / name).mkdir(parents=True, exist_ok=True)
        frames = []
        for i in range(n_frames):
            jitter = np.r_[rng.normal(0, .02, 2), rng.normal(0, .03)]
            T = look_at(pos[i] + jitter, tgt[i])
            img, depth = render(boxes, T, K, w, h)
            depth = depth * (1 + rng.normal(0, .004, depth.shape)).astype(np.float32)
            p = out_dir / name / f"{i:04d}.png"
            Image.fromarray(img).save(p)
            frames.append(Frame(img, depth, np.ones_like(depth), K.copy(), T, str(p)))
        scans_true.append(Scan(name, frames))

    # hide gravity, scale and origin like a feed-forward reconstruction does:
    # first "before" camera becomes the identity, scale becomes arbitrary.
    s = 0.37
    T0_inv = np.linalg.inv(scans_true[0].frames[0].T_wc)
    def sim(T):
        M = T0_inv @ T
        M[:3, 3] *= s
        return M
    scans = []
    for sc in scans_true:
        scans.append(Scan(sc.name, [replace(f, T_wc=sim(f.T_wc), depth=f.depth * s) for f in sc.frames]))
    meta = {"world_to_recon": (T0_inv, s)}
    return scans, meta
