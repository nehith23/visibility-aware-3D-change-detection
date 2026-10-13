"""Contact sheet of the inputs: evenly spaced keyframes of 'before' and 'after'.

    python scripts/input_strip.py <before frames or video> <after frames or video> out.jpg [n]
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def frames(src: str, n: int) -> list[Image.Image]:
    p = Path(src)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
        pick = np.linspace(0, len(files) - 1, n).round().astype(int)
        return [Image.open(files[i]).convert("RGB") for i in pick]
    cap = cv2.VideoCapture(str(p))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for i in np.linspace(0, total - 1, n + 2)[1:-1].round().astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            out.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    return out


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    before, after, out = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    rows = [("before", frames(before, n)), ("after", frames(after, n))]
    th = 180
    tiles = [[im.resize((round(im.width * th / im.height), th)) for im in ims] for _, ims in rows]
    label_w, gap = 90, 4
    W = label_w + max(sum(t.width for t in r) + gap * (len(r) - 1) for r in tiles)
    H = len(rows) * th + gap * (len(rows) - 1)
    sheet = Image.new("RGB", (W, H), (252, 252, 251))
    d = ImageDraw.Draw(sheet)
    f = font(18)
    for k, ((name, _), r) in enumerate(zip(rows, tiles)):
        y = k * (th + gap)
        d.text((10, y + th // 2 - 10), name, fill=(11, 11, 11), font=f)
        x = label_w
        for t in r:
            sheet.paste(t, (x, y))
            x += t.width + gap
    sheet.save(out, quality=85)
    print("wrote", out, sheet.size)


if __name__ == "__main__":
    main()
