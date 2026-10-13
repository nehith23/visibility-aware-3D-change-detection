"""Turn geometry + labels into plain English."""
from __future__ import annotations

import numpy as np

from .changes import Change, Region

DIRS = ["forward", "forward and to the right", "to the right", "back and to the right",
        "back", "back and to the left", "to the left", "forward and to the left"]


def direction(dx: float, dy: float) -> str:
    # room frame: +y = where the "before" recording started looking, +x = right
    ang = (np.degrees(np.arctan2(dx, dy)) + 360) % 360
    return DIRS[int((ang + 22.5) // 45) % 8]


def size_text(r: Region) -> str:
    L, W, H = r.dims
    cm = lambda x: int(round(100 * x / 5) * 5) or 5
    return f"about {cm(L)} x {cm(W)} x {cm(H)} cm"


def support_text(r: Region) -> str:
    b = r.bottom
    if b < 0.08:
        return "on the floor"
    return f"on a surface about {b:.2f} m high"


def where_text(r: Region) -> str:
    x, y = r.box_center[:2]
    fb = f"{abs(y):.1f} m {'ahead of' if y >= 0 else 'behind'}"
    if abs(x) < 0.3:
        return f"{fb} the starting point"
    return f"{fb} and {abs(x):.1f} m to the {'left' if x < 0 else 'right'} of the starting point"


GEOMETRIC = ("object", "small object", "large object")


def name(r: Region, other: Region | None = None) -> str:
    """Colour + label, hedged when CLIP is unsure."""
    src = other if other is not None and other.label_score > r.label_score else r
    lab, col, score = src.label, r.color_name, src.label_score
    if lab not in GEOMETRIC:
        if score < 0.12:
            from .semantics import fallback_label
            lab = fallback_label(r)
        elif score < 0.35:
            return f"{col} object (probably a {lab})" if col else f"object (probably a {lab})"
    if lab in ("small object", "large object"):
        size, noun = lab.split()
        return f"{size} {col} {noun}" if col else lab
    return f"{col} {lab}" if col else lab


def describe(c: Change) -> str:
    r = c.region
    if c.kind == "moved":
        t = c.target
        d = c.displacement
        dist = float(np.hypot(d[0], d[1]))
        s = f"The {name(r, t)} moved {dist:.1f} m {direction(d[0], d[1])}"
        if abs(d[2]) > 0.15:
            s += f", {'up' if d[2] > 0 else 'down'} {abs(d[2]):.1f} m"
        if c.rotation is not None and abs(c.rotation) >= 20:
            s += f", and turned about {abs(round(c.rotation / 5) * 5):.0f} degrees " \
                 f"{'anticlockwise' if c.rotation > 0 else 'clockwise'}"
        s += f". It now stands {support_text(t)}, {where_text(t)}."
        return s
    art = "An" if name(r)[0] in "aeiou" else "A"
    where = support_text(r)
    if c.kind == "added":
        verb = "appeared"
    else:
        verb = "was removed"
        where = where.replace("on the floor", "from the floor").replace("on a surface", "from a surface")
    return f"{art} {name(r)} ({size_text(r)}) {verb} {where}, {where_text(r)}."


HEADER = ("Directions are relative to where the 'before' recording starts, "
          "looking forward from the first frame.")
