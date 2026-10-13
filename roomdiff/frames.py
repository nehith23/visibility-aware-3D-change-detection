"""Pick sharp, evenly spread keyframes from a phone video."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("roomdiff")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}     # HLG (iPhone default) and PQ
SCALE_1080 = "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=bilinear"
# downscale first (cheap, stays 10-bit), then tone map at 1080p: ~4x faster than at 4K
SDR_FILTER = (SCALE_1080 + ",zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
              "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


VIDEO_EXT = (".mov", ".MOV", ".mp4", ".MP4", ".m4v")


def resolve_input(src: str | Path) -> Path:
    """A video, a folder of images, or a path without extension
    ('data/corridor/before_Left' finds before_Left.MOV)."""
    src = Path(src)
    if src.exists():
        return src
    for ext in VIDEO_EXT:
        if src.with_name(src.name + ext).exists():
            return src.with_name(src.name + ext)
    raise FileNotFoundError(f"no video or image folder at {src}")


def probe(src: str | Path) -> dict:
    """Video stream metadata via ffprobe, or {} if ffprobe is not installed."""
    import json
    import shutil
    import subprocess
    if not shutil.which("ffprobe"):
        return {}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,pix_fmt,color_transfer", "-of", "json", str(src)],
            capture_output=True, text=True, timeout=60, check=True).stdout
        return (json.loads(out).get("streams") or [{}])[0]
    except Exception:  # noqa: BLE001
        return {}


def is_hdr(info: dict) -> bool:
    return info.get("color_transfer") in HDR_TRANSFERS or "10" in info.get("pix_fmt", "")


def ensure_sdr(src: str | Path, cache_dir: str | Path) -> Path:
    """iPhones record 10-bit HDR (HLG) by default. OpenCV decodes it without
    tone mapping, which gives flat, washed-out colours and wrong colour names.
    Convert such videos once to 1080p SDR H.264 with ffmpeg; this also makes
    decoding 4K HEVC an order of magnitude faster."""
    import shutil
    import subprocess
    src = Path(src)
    if src.is_dir():
        return src
    info = probe(src)
    if not info:
        return src
    big = max(info.get("width", 0), info.get("height", 0)) > 2000
    if not (is_hdr(info) or big or info.get("codec_name") == "hevc"):
        return src
    out = Path(cache_dir) / f"{src.stem}_sdr.mp4"
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    if not shutil.which("ffmpeg"):
        log.warning("%s is HDR/HEVC/4K and ffmpeg is not installed, so colours will look washed out. "
                    "Install ffmpeg (Windows: winget install Gyan.FFmpeg) or record with "
                    "Formats > Most Compatible and HDR Video off.", src.name)
        return src
    out.parent.mkdir(parents=True, exist_ok=True)
    log.info("converting %s (%s, %sx%s) to 1080p SDR, once ...", src.name,
             info.get("color_transfer", "?"), info.get("width"), info.get("height"))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-an",
           "-vf", SDR_FILTER if is_hdr(info) else SCALE_1080,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=3600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("ffmpeg conversion failed (%s); using the original file.", e)
        return src
    return out


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_keyframes(src: str | Path, out_dir: str | Path, n: int, candidates_per_bin: int = 8) -> list[Path]:
    """Split the video into `n` equal time bins and keep the sharpest of a few
    candidate frames in each bin. Accepts a video file or a folder of images."""
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        imgs = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXT)
        if not imgs:
            raise FileNotFoundError(f"no images in {src}")
        idx = np.linspace(0, len(imgs) - 1, min(n, len(imgs))).round().astype(int)
        return [imgs[i] for i in idx]

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(
            f"OpenCV cannot open {src}. If it is an HEVC/HDR iPhone video, re-record with "
            "Settings > Camera > Formats > Most Compatible, or convert it: "
            "ffmpeg -i in.mov -vf scale=1920:-2 -c:v libx264 -crf 18 out.mp4")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        frames = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        total = len(frames)
        cap.release()
        cap = None
    bins = np.linspace(0, total, n + 1).astype(int)
    wanted = {}
    for b in range(n):
        lo, hi = bins[b], max(bins[b + 1], bins[b] + 1)
        for i in np.unique(np.linspace(lo, hi - 1, candidates_per_bin).astype(int)):
            wanted[int(i)] = b
    best = {}
    i = 0
    while True:
        if cap is not None:
            ok, frame = cap.read()
            if not ok:
                break
        else:
            if i >= total:
                break
            frame = frames[i]
        if i in wanted:
            b = wanted[i]
            small = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
            s = sharpness(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
            if b not in best or s > best[b][0]:
                best[b] = (s, frame)
        i += 1
    if cap is not None:
        cap.release()
    paths = []
    scores = []
    for b in sorted(best):
        p = out_dir / f"{b:04d}.jpg"
        cv2.imwrite(str(p), best[b][1], [cv2.IMWRITE_JPEG_QUALITY, 95])
        paths.append(p)
        scores.append(best[b][0])
    if scores:
        log.info("%s: %d keyframes from %d frames, sharpness median %.0f (min %.0f)",
                 src.name, len(paths), total, np.median(scores), np.min(scores))
        if np.median(scores) < 30:
            log.warning("%s looks blurry. Slower camera motion will improve results.", src.name)
    return paths


# --------------------------------------------------------------------------
# footage check
# --------------------------------------------------------------------------
def first_frame_size(src: str | Path) -> tuple[int, int]:
    """Upright (width, height) of a video or image folder."""
    src = Path(src)
    if src.is_dir():
        from PIL import Image, ImageOps
        p = next(p for p in sorted(src.iterdir()) if p.suffix.lower() in IMAGE_EXT)
        return ImageOps.exif_transpose(Image.open(p)).size
    cap = cv2.VideoCapture(str(src))
    ok, f = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"cannot read {src}")
    return f.shape[1], f.shape[0]


def check_video(src: str | Path, blur_threshold: float = 60.0) -> dict:
    """Score a recording before spending GPU time on it: resolution, blur,
    the longest stretch without a sharp frame, and whether the camera moved
    or only turned (parallax is what makes depth reliable)."""
    src = Path(src)
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {src}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    grays, sharp, i, size = [], [], 0, None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if size is None:
            size = (f.shape[1], f.shape[0])
        if i % 3 == 0:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            k = 576 / min(g.shape)
            g = cv2.resize(g, (round(g.shape[1] * k), round(g.shape[0] * k)))
            sharp.append(sharpness(g))
            grays.append(g)
        i += 1
    cap.release()
    sharp = np.array(sharp)
    # Absolute sharpness confuses blur with blank surfaces (a plain wall or a
    # closed blind is sharp but has no texture). Judge blur relative to the
    # best frames within +-1.5 s, and report low texture separately.
    half = max(1, int(1.5 * fps / 3))
    local_best = np.array([np.percentile(sharp[max(0, k - half):k + half + 1], 90)
                           for k in range(len(sharp))])
    low_texture = local_best < blur_threshold
    blurry = (sharp < 0.4 * local_best) & ~low_texture
    unusable = blurry | (low_texture & (sharp < 15))

    def longest(mask):
        run = best = 0
        for b in mask:
            run = run + 1 if b else 0
            best = max(best, run)
        return best

    gap = longest(unusable)
    tex_gap = longest(low_texture)

    orb = cv2.ORB_create(2000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    step = max(1, int(0.5 * fps / 3))
    ratios = []
    for a in range(0, len(grays) - step, step):
        if unusable[a] or unusable[a + step] or low_texture[a] or low_texture[a + step]:
            continue
        k1, d1 = orb.detectAndCompute(grays[a], None)
        k2, d2 = orb.detectAndCompute(grays[a + step], None)
        if d1 is None or d2 is None:
            continue
        m = bf.match(d1, d2)
        if len(m) < 60:
            continue
        p1 = np.float32([k1[x.queryIdx].pt for x in m])
        p2 = np.float32([k2[x.trainIdx].pt for x in m])
        _, hm = cv2.findHomography(p1, p2, cv2.RANSAC, 2.0)
        _, fm = cv2.findFundamentalMat(p1, p2, cv2.FM_RANSAC, 1.0, 0.999)
        if hm is not None and fm is not None and fm.sum() > 0:
            ratios.append(hm.sum() / fm.sum())
    rot = float(np.median(ratios)) if ratios else float("nan")

    dur = i / fps
    rep = {"file": src.name, "width": size[0], "height": size[1],
           "orientation": "landscape" if size[0] >= size[1] else "portrait",
           "duration_s": round(dur, 1), "fps": round(fps, 1),
           "blurry_share": round(float(blurry.mean()), 2),
           "longest_blurry_gap_s": round(gap * 3 / fps, 1),
           "low_texture_share": round(float(low_texture.mean()), 2),
           "longest_low_texture_s": round(tex_gap * 3 / fps, 1),
           "rotation_only_score": round(rot, 2)}
    tips = []
    if min(size) < 720:
        tips.append(f"Resolution {size[0]}x{size[1]} is low. Transfer the original file "
                    "(AirDrop, cable or iCloud Drive), not through a chat app.")
    if not 20 <= dur <= 75:
        tips.append(f"{dur:.0f} s long. Aim for 30 to 60 s.")
    if blurry.mean() > 0.2:
        tips.append(f"{100 * blurry.mean():.0f}% of frames are blurry. Move and turn more slowly.")
    if gap * 3 / fps > 2.0:
        tips.append(f"No sharp frame for {gap * 3 / fps:.1f} s in a row, so part of the room has no "
                    "usable view. Slow down there, especially when turning.")
    if tex_gap * 3 / fps > 4.0:
        tips.append(f"{tex_gap * 3 / fps:.1f} s in a row of blank surfaces (plain wall, blind, door). "
                    "Not wasted, but keep some furniture or an edge in frame so it can be placed.")
    if rot == rot and rot > 0.8:
        tips.append("Mostly rotation (or large flat walls, which score the same). Where you can, "
                    "step sideways while filming. Depth comes from the camera moving, not rotating.")
    info = probe(src)
    if info and is_hdr(info):
        tips.append(f"Recorded in HDR ({info.get('color_transfer')}). The pipeline converts it, but "
                    "set Settings > Camera > Record Video > HDR Video off for the next take.")
    rep["tips"] = tips
    severe = min(size) < 480 or gap * 3 / fps > 4.0 or blurry.mean() > 0.35
    rep["verdict"] = "re-record" if severe else ("good" if not tips else "usable")
    return rep
