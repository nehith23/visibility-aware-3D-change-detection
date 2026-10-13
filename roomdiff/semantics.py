"""Semantic labels for change regions.

For each region we pick the frame that sees it best, crop the full-resolution
video frame around it, and label the crop with CLIP. CLIP alone happily calls a
40 cm box a "wardrobe", so the scores are combined with a size prior from the
3D geometry. That keeps the label consistent with the measured object.
Crops that CLIP thinks are bare wall, floor or a shadow are flagged as likely
artefacts.
"""
from __future__ import annotations

import colorsys
import logging
from functools import lru_cache

import numpy as np
from PIL import Image

from .changes import Change, Region
from .config import Config
from .geometry import project
from .scene import Frame, Scan

log = logging.getLogger("roomdiff")

# label -> (min height, max height) in metres. Loose on purpose: a region may
# be only partly observed, so its measured size can be smaller than the object.
SIZE_PRIOR = {
    "chair": (0.35, 1.4), "office chair": (0.5, 1.4), "stool": (0.3, 0.9),
    "table": (0.35, 1.2), "desk": (0.5, 1.2), "bed": (0.25, 1.3), "sofa": (0.4, 1.1),
    "pillow": (0.05, 0.4), "blanket": (0.02, 0.5), "cushion": (0.05, 0.4),
    "backpack": (0.15, 0.7), "bag": (0.1, 0.7), "handbag": (0.1, 0.45),
    "suitcase": (0.2, 0.9), "cardboard box": (0.05, 0.8), "storage box": (0.05, 0.8),
    "laundry basket": (0.2, 0.8), "trash can": (0.15, 0.9), "bottle": (0.05, 0.45),
    "water bottle": (0.1, 0.4), "mug": (0.04, 0.2), "cup": (0.04, 0.2), "bowl": (0.03, 0.2),
    "book": (0.01, 0.35), "stack of books": (0.05, 0.6), "laptop": (0.01, 0.4),
    "computer monitor": (0.2, 0.7), "keyboard": (0.01, 0.08), "lamp": (0.2, 1.9),
    "potted plant": (0.1, 1.8), "pair of shoes": (0.05, 0.3), "jacket": (0.05, 1.2),
    "pile of clothes": (0.03, 0.8), "towel": (0.01, 1.0), "guitar": (0.3, 1.3),
    "speaker": (0.1, 1.2), "television": (0.25, 1.2), "picture frame": (0.1, 1.0),
    "clock": (0.1, 0.5), "electric fan": (0.25, 1.4), "heater": (0.2, 1.0),
    "vacuum cleaner": (0.2, 1.3), "toy": (0.03, 0.6), "ball": (0.05, 0.4),
    "umbrella": (0.2, 1.2), "helmet": (0.15, 0.4), "bicycle": (0.6, 1.3),
    "drawer unit": (0.3, 1.4), "cabinet": (0.4, 2.2), "mirror": (0.3, 2.0),
    "headphones": (0.05, 0.25), "kettle": (0.15, 0.35), "food container": (0.03, 0.3),
    "shopping bag": (0.15, 0.6), "basket": (0.1, 0.6), "door": (1.0, 2.3),
    "rug": (0.0, 0.05), "game controller": (0.02, 0.1), "printer": (0.15, 0.5),
}
STRUCTURE = ["plain wall", "bare floor", "ceiling", "window", "shadow on a wall", "blurry photo"]
TEMPLATES = ["a photo of a {}.", "a cropped photo of a {}.", "a photo of a {} in a room."]

COLOR_NAMES = [
    ("red", 0), ("orange", 25), ("yellow", 55), ("green", 120), ("teal", 175),
    ("blue", 220), ("purple", 275), ("pink", 330), ("red", 360),
]


def color_name(rgb: np.ndarray) -> str:
    r, g, b = (np.median(rgb.reshape(-1, 3), 0) / 255).tolist()
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l > 0.82:
        return "white"
    if l < 0.16:
        return "black"
    if s < 0.18:
        return "grey" if l > 0.35 else "dark grey"
    hue = h * 360
    if 15 <= hue <= 45 and l < 0.55:
        return "brown" if s < 0.75 or l < 0.4 else "orange"
    name = min(COLOR_NAMES, key=lambda c: abs(c[1] - hue))[0]
    return ("dark " + name) if l < 0.3 else name


# --------------------------------------------------------------------------
# evidence views
# --------------------------------------------------------------------------
def _visible(points: np.ndarray, f: Frame, tol: float = 0.06):
    H, W = f.hw
    u, v, z = project(points, f)
    ok = (z > 0.05) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    d = f.depth[np.clip(v, 0, H - 1).astype(int), np.clip(u, 0, W - 1).astype(int)]
    vis = ok & (np.abs(d - z) < np.maximum(tol, 0.04 * z))
    return u, v, z, vis


def best_view(points: np.ndarray, scan: Scan, mode: str = "visible"):
    """Frame index and pixel box that show `points` best.
    mode="visible": the points themselves are visible (object present).
    mode="footprint": the region is in view and nothing blocks it (empty spot)."""
    best, best_score = None, -1.0
    for i, f in enumerate(scan.frames):
        H, W = f.hw
        u, v, z, vis = _visible(points, f)
        if mode == "visible":
            sel = vis
        else:
            inb = (z > 0.05) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            d = f.depth[np.clip(v, 0, H - 1).astype(int), np.clip(u, 0, W - 1).astype(int)]
            sel = inb & (d > z - 0.05)                 # not occluded
        n = sel.sum()
        if n < 5:
            continue
        cu, cv = u[sel].mean() / W - .5, v[sel].mean() / H - .5
        frac = n / len(points)
        score = frac * (1 - 1.2 * (cu ** 2 + cv ** 2)) * min(1.0, 2.5 / max(np.median(z[sel]), 0.3))
        if score > best_score:
            best_score = score
            best = (i, np.array([u[sel].min(), v[sel].min(), u[sel].max(), v[sel].max()]))
    return best


def crop_full(f: Frame, box: np.ndarray, pad: float = 0.35, min_px: int = 96):
    """Crop the full-resolution video frame around a small-image pixel box.
    Returns the crop and the box position inside it (for drawing an outline)."""
    sx, ox, sy, oy = f.full_affine
    try:
        img = Image.open(f.full_path).convert("RGB") if f.full_path else None
    except OSError:
        img = None
    if img is None:
        img = Image.fromarray(f.image)
        sx, ox, sy, oy = 1.0, 0.0, 1.0, 0.0
    x0, y0, x1, y1 = box[0] * sx + ox, box[1] * sy + oy, box[2] * sx + ox, box[3] * sy + oy
    w, h = x1 - x0, y1 - y0
    side = max(w, h) * (1 + 2 * pad)
    side = max(side, min_px * max(sx, 1.0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    W, H = img.size
    side = min(side, W, H)
    bx = (x0, y0, x1, y1)
    x0 = int(np.clip(cx - side / 2, 0, W - side))
    y0 = int(np.clip(cy - side / 2, 0, H - side))
    out = img.crop((x0, y0, x0 + int(side), y0 + int(side)))
    k = 1.0
    if out.size[0] < 224:
        k = 224 / out.size[0]
        out = out.resize((224, 224), Image.BICUBIC)
    inner = [(bx[0] - x0) * k, (bx[1] - y0) * k, (bx[2] - x0) * k, (bx[3] - y0) * k]
    return out, inner


def box_pixels(corners: np.ndarray, f: Frame):
    u, v, z = project(corners, f)
    if (z <= 0.05).any():
        return None
    H, W = f.hw
    b = np.array([u.min(), v.min(), u.max(), v.max()])
    b[[0, 2]] = np.clip(b[[0, 2]], 0, W - 1)
    b[[1, 3]] = np.clip(b[[1, 3]], 0, H - 1)
    if b[2] - b[0] < 2 or b[3] - b[1] < 2:
        return None
    return b


# --------------------------------------------------------------------------
# CLIP
# --------------------------------------------------------------------------
class ClipLabeler:
    def __init__(self, cfg: Config):
        import open_clip
        import torch
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        pretrained = cfg.clip_pretrained or None
        model, _, self.preprocess = open_clip.create_model_and_transforms(cfg.clip_model, pretrained=pretrained)
        self.model = model.eval().to(self.device)
        tok = open_clip.get_tokenizer(cfg.clip_model)
        self.labels = list(SIZE_PRIOR) + STRUCTURE
        with torch.no_grad():
            feats = []
            for lab in self.labels:
                t = tok([tpl.format(lab) for tpl in TEMPLATES]).to(self.device)
                e = self.model.encode_text(t).float()
                e = e / e.norm(dim=-1, keepdim=True)
                e = e.mean(0)
                feats.append(e / e.norm())
            self.text = self.torch.stack(feats)

    def embed(self, img: Image.Image) -> np.ndarray:
        with self.torch.no_grad():
            x = self.preprocess(img).unsqueeze(0).to(self.device)
            e = self.model.encode_image(x).float()
            e = e / e.norm(dim=-1, keepdim=True)
        return e[0].cpu().numpy()

    def label(self, emb: np.ndarray, height: float):
        sims = self.text.cpu().numpy() @ emb
        logits = 100.0 * sims
        p = np.exp(logits - logits.max())
        p /= p.sum()
        prior = np.ones(len(self.labels))
        for k, lab in enumerate(self.labels):
            if lab in SIZE_PRIOR:
                lo, hi = SIZE_PRIOR[lab]
                if height > hi * 1.3 or height < lo * 0.4:
                    prior[k] = 0.15
        post = p * prior
        post /= post.sum()
        k = int(post.argmax())
        return self.labels[k], float(post[k]), self.labels[k] in STRUCTURE


@lru_cache(maxsize=1)
def _get_clip(model: str, pretrained: str):
    cfg = Config(clip_model=model, clip_pretrained=pretrained)
    return ClipLabeler(cfg)


def fallback_label(r: Region) -> str:
    L, Wd, Hh = r.dims
    if Hh > 1.2 or L > 1.5:
        return "large object"
    if max(L, Hh) < 0.25:
        return "small object"
    return "object"


def annotate(regions: list[Region], scans: dict[str, Scan], cfg: Config) -> list[Region]:
    """Attach crops, CLIP embeddings, labels and colour names to regions.
    Returns regions that look like artefacts (bare wall/floor) separately."""
    clip = None
    if cfg.use_clip:
        try:
            clip = _get_clip(cfg.clip_model, cfg.clip_pretrained)
        except Exception as e:  # noqa: BLE001 - CLIP is optional
            log.warning("CLIP unavailable (%s). Falling back to geometric labels.", e)
    artefacts = []
    for r in regions:
        r.color_name = color_name(r.colors)
        view = best_view(r.points, scans[r.scan], "visible")
        if view is not None:
            i, box = view
            f = scans[r.scan].frames[i]
            img, inner = crop_full(f, box)
            r.evidence["self"] = {"frame": i, "box": box.tolist(), "image": img, "outline": inner}
        if clip is not None and "self" in r.evidence:
            r.embedding = clip.embed(r.evidence["self"]["image"])
            r.label, r.label_score, is_struct = clip.label(r.embedding, float(r.dims[2]))
            if is_struct and r.label_score > 0.5:
                artefacts.append(r)
            elif r.label in SIZE_PRIOR:
                # the name must agree with the measured geometry: a 60 cm tall
                # "door" is a fragment of something, so call it an object and
                # keep CLIP's guess in the report
                lo, hi = SIZE_PRIOR[r.label]
                h = float(r.dims[2])
                if h < 0.7 * lo or h > 1.5 * hi:
                    r.evidence["clip_guess"] = {"label": r.label, "score": round(r.label_score, 3),
                                                "why_not_used": f"{100 * h:.0f} cm tall, a {r.label} is "
                                                                f"{100 * lo:.0f} to {100 * hi:.0f} cm"}
                    r.label, r.label_score = fallback_label(r), 0.0
        else:
            r.label = fallback_label(r)
    return artefacts


def counter_evidence(changes: list[Change], scans: dict[str, Scan]) -> None:
    """For each change, find the view in the *other* recording that shows the
    same spot, so the report can show before/after side by side."""
    for c in changes:
        r = c.region
        other = "after" if r.scan == "before" else "before"
        if c.kind == "moved":
            t = c.target
            view = best_view(t.points, scans["after"], "visible")
            if view is not None:
                i, box = view
                img, inner = crop_full(scans["after"].frames[i], box)
                t.evidence["self"] = {"frame": i, "box": box.tolist(), "image": img, "outline": inner}
            continue
        view = best_view(r.points, scans[other], "footprint")
        if view is None:
            continue
        i, _ = view
        f = scans[other].frames[i]
        box = box_pixels(r.corners, f)
        if box is None:
            continue
        img, inner = crop_full(f, box, pad=0.6)
        r.evidence["other"] = {"frame": i, "box": box.tolist(), "image": img, "outline": inner}
