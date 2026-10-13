"""Outputs: interactive 3D page, top-down change map, evidence sheet, PLY files.

Colour roles (validated categorical slots 1 to 3, all-pairs CVD safe):
moved = blue, removed = orange, added = aqua. Unobserved space is a neutral
grey with hatching, so it never reads as a change. Every change also carries a
numbered label, so colour is never the only cue.
"""
from __future__ import annotations

import html
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["hatch.color"] = "#b9b7ae"
plt.rcParams["hatch.linewidth"] = 0.7
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Polygon  # noqa: E402

from .changes import AMBIGUOUS, GONE, PRESENT, UNOBSERVED, Change, DetectionResult  # noqa: E402

COL = {"moved": "#2a78d6", "removed": "#eb6834", "added": "#1baf7a"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#9a9890", "#e7e6e2", "#fcfcfb"
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]


def _context(res: DetectionResult, max_pts: int, rng):
    pts, cols = [], []
    for name in ("before", "after"):
        p, c = res.clouds[name]
        st = res.states[name]
        keep = (st == PRESENT) | (st == AMBIGUOUS)
        keep &= p[:, 2] < 2.1                          # hide the ceiling
        pts.append(p[keep])
        cols.append(c[keep])
    p, c = np.concatenate(pts), np.concatenate(cols)
    if len(p) > max_pts:
        sel = rng.choice(len(p), max_pts, replace=False)
        p, c = p[sel], c[sel]
    return p, c


def _unobserved(res: DetectionResult):
    p, _ = res.clouds["before"]
    st = res.states["before"]
    m = (st == UNOBSERVED) & (p[:, 2] < 2.1)
    return p[m]


# --------------------------------------------------------------------------
# interactive 3D page
# --------------------------------------------------------------------------
def scene_html(res: DetectionResult, changes: list[Change], scans, path: Path,
               summary: dict, max_pts: int = 70_000):
    import plotly.graph_objects as go

    rng = np.random.default_rng(0)
    fig = go.Figure()
    p, c = _context(res, max_pts, rng)
    rgb = [f"rgb({int(r)},{int(g)},{int(b)})" for r, g, b in c]
    fig.add_trace(go.Scatter3d(x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="markers",
                               marker=dict(size=1.6, color=rgb, opacity=0.55),
                               name="Unchanged surfaces", hoverinfo="skip"))
    u = _unobserved(res)
    if len(u) > 25_000:
        u = u[rng.choice(len(u), 25_000, replace=False)]
    fig.add_trace(go.Scatter3d(x=u[:, 0], y=u[:, 1], z=u[:, 2], mode="markers",
                               marker=dict(size=1.6, color=MUTED, opacity=0.35),
                               name="Not seen in 'after' (unverified)", hoverinfo="skip",
                               visible="legendonly"))

    raw = np.concatenate([res.clouds[n][0][res.states[n] == GONE] for n in ("before", "after")])
    if len(raw):
        fig.add_trace(go.Scatter3d(x=raw[:, 0], y=raw[:, 1], z=raw[:, 2], mode="markers",
                                   marker=dict(size=2, color=INK2, opacity=0.6),
                                   name="Raw change evidence (before clustering)", hoverinfo="skip",
                                   visible="legendonly"))

    shown = set()
    for ch in changes:
        col = COL[ch.kind] if ch.confident else MUTED
        regs = [(ch.region, "solid")] + ([(ch.target, "solid")] if ch.target is not None else [])
        if ch.kind == "moved":
            regs[0] = (ch.region, "dash")
        for k, (r, dash) in enumerate(regs):
            key = ch.kind if ch.confident else "lowconf"
            first = key not in shown
            shown.add(key)
            pts = r.points
            if len(pts) > 4000:
                pts = pts[rng.choice(len(pts), 4000, replace=False)]
            fig.add_trace(go.Scatter3d(
                x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="markers",
                marker=dict(size=2.4, color=col, opacity=0.35 if dash == "dash" else 0.9),
                name=ch.kind.capitalize() if ch.confident else "Low confidence",
                legendgroup=ch.kind if ch.confident else "lowconf", showlegend=first and k == 0,
                hovertext=f"#{ch.id} {ch.description}", hoverinfo="text"))
            xs, ys, zs = [], [], []
            for a, b in EDGES:
                xs += [r.corners[a, 0], r.corners[b, 0], None]
                ys += [r.corners[a, 1], r.corners[b, 1], None]
                zs += [r.corners[a, 2], r.corners[b, 2], None]
            fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                                       line=dict(color=col, width=5, dash=dash),
                                       legendgroup=ch.kind, showlegend=False, hoverinfo="skip"))
        top = (ch.target or ch.region)
        fig.add_trace(go.Scatter3d(
            x=[top.box_center[0]], y=[top.box_center[1]], z=[top.top + 0.12], mode="text",
            text=[f"<b>#{ch.id}</b> {html.escape(ch.region.label if ch.target is None else _lab(ch))}"],
            textfont=dict(color=INK, size=13), legendgroup=ch.kind, showlegend=False,
            hovertext=ch.description, hoverinfo="text"))
        if ch.kind == "moved":
            a = ch.region.box_center.copy()
            b = ch.target.box_center.copy()
            a[2] = b[2] = max(ch.region.top, ch.target.top) + 0.05
            fig.add_trace(go.Scatter3d(x=[a[0], b[0]], y=[a[1], b[1]], z=[a[2], b[2]], mode="lines",
                                       line=dict(color=col, width=7), legendgroup="moved",
                                       showlegend=False, hoverinfo="skip"))
            d = (b - a) / (np.linalg.norm(b - a) + 1e-9)
            fig.add_trace(go.Cone(x=[b[0]], y=[b[1]], z=[b[2]], u=[d[0]], v=[d[1]], w=[d[2]],
                                  sizemode="absolute", sizeref=0.18, anchor="tip",
                                  colorscale=[[0, col], [1, col]], showscale=False,
                                  legendgroup="moved", showlegend=False, hoverinfo="skip"))

    for name, dash, col in (("before", "solid", INK2), ("after", "dash", MUTED)):
        cc = scans[name].camera_centers()
        fig.add_trace(go.Scatter3d(x=cc[:, 0], y=cc[:, 1], z=cc[:, 2], mode="lines+markers",
                                   line=dict(color=col, width=4, dash=dash), marker=dict(size=2.5, color=col),
                                   name=f"Camera path, {name}", hoverinfo="skip"))

    axis = dict(showbackground=False, gridcolor=GRID, zerolinecolor=GRID, color=INK2, title="")
    fig.update_layout(
        scene=dict(xaxis=axis, yaxis=axis, zaxis=axis, aspectmode="data",
                   camera=dict(eye=dict(x=-0.9, y=-1.6, z=1.3))),
        paper_bgcolor=SURFACE, margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(252,252,251,0.85)", font=dict(color=INK, size=12)),
        font=dict(family="Inter, system-ui, sans-serif"),
    )
    plot = fig.to_html(full_html=False, include_plotlyjs=True, config={"displaylogo": False})
    def item(c):
        bg = COL[c.kind] if c.confident else MUTED
        note = "" if c.confident else ' <span class="weak">low confidence</span>'
        return (f'<li class="{"" if c.confident else "lc"}"><span class="tag" style="background:{bg}">#{c.id} {c.kind}</span>'
                f'<span class="conf">{c.confidence:.2f}</span>{note}<p>{html.escape(c.description)}</p></li>')
    strong = [c for c in changes if c.confident]
    weak = [c for c in changes if not c.confident]
    items = "\n".join(item(c) for c in strong) or "<li><p>No confident changes.</p></li>"
    if weak:
        items += '\n<li class="hdr">Possible changes (low confidence), usually reconstruction noise</li>\n'
        items += "\n".join(item(c) for c in weak)
    cov = summary.get("coverage", {})
    page = TEMPLATE.format(
        plot=plot, items=items, n=len(strong), nweak=len(weak),
        verified=f"{100 * cov.get('before_verified', 0):.0f}",
        scale=f"{summary.get('scale', 1):.2f}",
    )
    path.write_text(page, encoding="utf-8")


def _lab(ch: Change) -> str:
    r, t = ch.region, ch.target
    return t.label if t is not None and t.label_score > r.label_score else r.label


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What changed in the room</title>
<style>
:root{{--ink:#0b0b0b;--ink2:#52514e;--surface:#fcfcfb;--line:#e7e6e2}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,sans-serif;color:var(--ink);background:var(--surface)}}
.wrap{{display:grid;grid-template-columns:minmax(0,1fr) 360px;height:100vh}}
.plot{{min-height:60vh}}.plot>div{{height:100%}}
aside{{border-left:1px solid var(--line);padding:22px 20px;overflow:auto}}
h1{{font-size:19px;margin:0 0 4px}}.sub{{color:var(--ink2);font-size:13px;margin:0 0 18px;line-height:1.45}}
ul{{list-style:none;padding:0;margin:0}}li{{padding:12px 0;border-top:1px solid var(--line)}}
li p{{margin:6px 0 0;font-size:14px;line-height:1.45}}
.tag{{display:inline-block;color:#fff;font-size:12px;font-weight:600;padding:2px 8px;border-radius:4px;text-transform:capitalize}}
.conf{{font-size:12px;color:var(--ink2);margin-left:8px}}.weak{{font-size:12px;color:var(--ink2);font-style:italic}}
li.lc p{{color:var(--ink2)}}li.hdr{{font-size:12px;font-weight:600;color:var(--ink2);text-transform:uppercase;letter-spacing:.04em;padding-top:18px}}
.foot{{color:var(--ink2);font-size:12px;margin-top:18px;line-height:1.5}}
@media (max-width:900px){{.wrap{{grid-template-columns:1fr;height:auto}}.plot{{height:70vh}}aside{{border-left:0;border-top:1px solid var(--line)}}}}
</style></head><body><div class="wrap"><div class="plot">{plot}</div>
<aside><h1>What changed in the room</h1>
<p class="sub">{n} change(s) found, plus {nweak} low-confidence candidate(s). {verified}% of the 'before' surfaces were re-observed in 'after'.
Turn on "Not seen in 'after'" in the legend to see where nothing can be claimed.</p>
<ul>{items}</ul>
<p class="foot">Dashed box = old position. Units are metres, estimated scale factor {scale}.
Directions are relative to the first frame of the 'before' recording.</p></aside></div></body></html>"""


# --------------------------------------------------------------------------
# top-down map
# --------------------------------------------------------------------------
def topdown_png(res: DetectionResult, changes: list[Change], scans, path: Path, cell: float = 0.04):
    p_ctx, _ = _context(res, 400_000, np.random.default_rng(1))
    u = _unobserved(res)
    cams = np.concatenate([scans[n].camera_centers() for n in ("before", "after")])
    allp = np.concatenate([p_ctx, u, cams]) if len(u) else np.concatenate([p_ctx, cams])
    lo = np.minimum(np.percentile(allp[:, :2], 0.5, axis=0), cams[:, :2].min(0)) - 0.3
    hi = np.maximum(np.percentile(allp[:, :2], 99.5, axis=0), cams[:, :2].max(0)) + 0.3
    shape = np.ceil((hi - lo) / cell).astype(int) + 1

    def grid(points, reduce_max=True):
        g = np.full(shape[::-1], np.nan)
        ij = np.floor((points[:, :2] - lo) / cell).astype(int)
        ok = (ij >= 0).all(1) & (ij < shape).all(1)
        ij, z = ij[ok], points[ok, 2]
        order = np.argsort(z)
        g[ij[order, 1], ij[order, 0]] = z[order]
        return g

    hmap = grid(p_ctx)
    fig, ax = plt.subplots(figsize=(9, 9 * shape[1] / shape[0] + 0.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ext = [lo[0], lo[0] + shape[0] * cell, lo[1], lo[1] + shape[1] * cell]
    ax.imshow(np.clip(hmap, 0, 2.0), origin="lower", extent=ext, cmap="Greys", vmin=-0.6, vmax=2.2,
              interpolation="nearest")
    if len(u):
        ug = grid(u)
        seen = ~np.isnan(hmap)
        mask = (~np.isnan(ug)) & ~seen
        if mask.any():
            xs = np.linspace(ext[0], ext[1], shape[0])
            ys = np.linspace(ext[2], ext[3], shape[1])
            ax.contourf(xs, ys, mask.astype(float), levels=[0.5, 1.5], colors="none",
                        hatches=["////"], zorder=2)
            ax.contourf(xs, ys, mask.astype(float), levels=[0.5, 1.5], colors=[MUTED], alpha=0.18, zorder=2)

    for name, ls in (("before", "-"), ("after", "--")):
        cc = scans[name].camera_centers()
        ax.plot(cc[:, 0], cc[:, 1], ls, color=INK2 if name == "before" else MUTED, lw=2, zorder=3)
        ax.plot(cc[0, 0], cc[0, 1], "o", color=INK2 if name == "before" else MUTED, ms=6, zorder=3)
        ax.annotate(f"{name} start", cc[0, :2], xytext=(6, 6), textcoords="offset points",
                    fontsize=8, color=INK2)

    for ch in changes:
        col = COL[ch.kind]
        r = ch.region
        if not ch.confident:
            # low-confidence candidates: faint dashed outline, "?" label
            reg = ch.target if ch.target is not None else r
            ax.add_patch(Polygon(reg.corners[:4, :2], closed=True, fill=False, ec=col, lw=1, ls=":",
                                 alpha=.8, zorder=4))
            ax.annotate(f"{ch.id}?", reg.box_center[:2], xytext=(6, 6), textcoords="offset points",
                        fontsize=8, color=INK2, zorder=6)
            continue
        if ch.kind == "moved":
            ax.add_patch(Polygon(r.corners[:4, :2], closed=True, fill=False, ec=col, lw=2, ls="--", zorder=4))
            t = ch.target
            ax.add_patch(Polygon(t.corners[:4, :2], closed=True, fc=col, ec=col, alpha=.35, lw=0, zorder=4))
            ax.add_patch(Polygon(t.corners[:4, :2], closed=True, fill=False, ec=col, lw=2, zorder=5))
            ax.add_patch(FancyArrowPatch(r.box_center[:2], t.box_center[:2], arrowstyle="-|>",
                                         mutation_scale=16, color=col, lw=2, zorder=5,
                                         shrinkA=4, shrinkB=4))
            anchor = t.box_center[:2]
        else:
            ax.add_patch(Polygon(r.corners[:4, :2], closed=True, fc=col, ec=col, alpha=.35, lw=0, zorder=4))
            ax.add_patch(Polygon(r.corners[:4, :2], closed=True, fill=False, ec=col, lw=2, zorder=5))
            anchor = r.box_center[:2]
        ax.annotate(f"#{ch.id}", anchor, xytext=(9, 9), textcoords="offset points", fontsize=10,
                    fontweight="bold", color=INK, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=col, lw=1.2))

    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [Patch(fc=COL["moved"], alpha=.5, ec=COL["moved"], label="Moved (dashed = old spot)"),
               Patch(fc=COL["removed"], alpha=.5, ec=COL["removed"], label="Removed"),
               Patch(fc=COL["added"], alpha=.5, ec=COL["added"], label="Added"),
               Patch(fc=MUTED, alpha=.25, hatch="////", ec=MUTED, label="Not seen in 'after'"),
               Patch(fill=False, ec=INK2, ls=":", label="Low confidence (n?)"),
               Line2D([], [], color=INK2, lw=2, label="Camera path, before"),
               Line2D([], [], color=MUTED, lw=2, ls="--", label="Camera path, after")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=3, frameon=False,
              fontsize=9, labelcolor=INK)
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.set_xlabel("metres (right)", color=INK2, fontsize=9)
    ax.set_ylabel("metres (forward)", color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.set_title("Top-down change map  (darker = taller)", color=INK, fontsize=12, loc="left")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------------
# evidence sheet
# --------------------------------------------------------------------------
def evidence_png(changes: list[Change], path: Path):
    if not changes:
        return
    n = len(changes)
    fig, axes = plt.subplots(n, 3, figsize=(11, 3.1 * n), dpi=120,
                             gridspec_kw=dict(width_ratios=[1.35, 1, 1]))
    axes = np.atleast_2d(axes)
    fig.patch.set_facecolor(SURFACE)
    for row, ch in zip(axes, changes):
        col = COL[ch.kind]
        if ch.kind == "moved":
            before = ch.region.evidence.get("self")
            after = ch.target.evidence.get("self")
        elif ch.kind == "removed":
            before, after = ch.region.evidence.get("self"), ch.region.evidence.get("other")
        else:
            before, after = ch.region.evidence.get("other"), ch.region.evidence.get("self")
        row[0].axis("off")
        tag = "" if ch.confident else "   (low confidence)"
        row[0].text(0, .92, f"#{ch.id}  {ch.kind.upper()}{tag}", color=col, fontsize=13, fontweight="bold",
                    va="top", transform=row[0].transAxes)
        row[0].text(0, .72, textwrap.fill(ch.description, 40), color=INK, fontsize=10, va="top",
                    transform=row[0].transAxes, linespacing=1.4)
        for ax, ev, title in ((row[1], before, "before"), (row[2], after, "after")):
            ax.set_xticks([])
            ax.set_yticks([])
            for s in ax.spines.values():
                s.set_color(col)
                s.set_linewidth(2)
            if ev is None:
                ax.set_facecolor("#f1f0ec")
                ax.text(.5, .5, "no clear view", ha="center", va="center", color=INK2, fontsize=9,
                        transform=ax.transAxes)
            else:
                ax.imshow(ev["image"])
                x0, y0, x1, y1 = ev["outline"]
                ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=col, lw=1.6,
                                           ls="--" if title != ("after" if ch.kind == "added" else "before")
                                           and ch.kind != "moved" else "-"))
            ax.set_title(title, fontsize=9, color=INK2, loc="left")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------------
# PLY + reports
# --------------------------------------------------------------------------
def write_ply(path: Path, pts: np.ndarray, cols: np.ndarray):
    pts = pts.astype("<f4")
    cols = np.clip(cols, 0, 255).astype("u1")
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(pts)}\nproperty float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    rec = np.empty(len(pts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                    ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = pts.T
    rec["r"], rec["g"], rec["b"] = cols.T
    with open(path, "wb") as f:
        f.write(header.encode())
        f.write(rec.tobytes())


def hex_rgb(h: str):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def change_cloud(res: DetectionResult, changes: list[Change]):
    p, c = _context(res, 600_000, np.random.default_rng(2))
    c = c * 0.6 + 255 * 0.4                           # fade context
    extra_p, extra_c = [p], [c]
    for ch in changes:
        for r in [ch.region] + ([ch.target] if ch.target is not None else []):
            extra_p.append(r.points)
            extra_c.append(np.tile(hex_rgb(COL[ch.kind]), (len(r.points), 1)))
    return np.concatenate(extra_p), np.concatenate(extra_c)


def report(changes, summary: dict, out: Path, header: str):
    data = {"summary": summary, "changes": []}
    lines = ["# What changed in the room", "", header, ""]
    cov = summary["coverage"]
    n_conf = sum(c.confident for c in changes)
    lines += [f"* Changes found: **{n_conf}** (plus {len(changes) - n_conf} low-confidence candidates)",
              f"* Share of 'before' surfaces re-observed in 'after': {100 * cov['before_verified']:.0f}%",
              f"* Share of 'after' surfaces observed in 'before': {100 * cov['after_verified']:.0f}%",
              f"* Metric scale factor: {summary['scale']:.3f} (from a {summary['camera_height']} m camera height assumption)",
              ""]
    for ch in changes:
        r = ch.region
        e = {"id": ch.id, "type": ch.kind, "label": _lab(ch) if ch.target is not None else r.label,
             "label_score": round(max(r.label_score, ch.target.label_score if ch.target else 0), 3),
             "color": r.color_name, "description": ch.description,
             "box": {"center": np.round(r.box_center, 3).tolist(), "size": np.round(r.dims, 3).tolist(),
                     "yaw_deg": round(r.yaw, 1)},
             "points": int(len(r.points)), "confidence": round(ch.confidence, 2)}
        def _ev(reg):
            ev = reg.evidence
            out = {k: (round(float(ev[k]), 3) if k != "see_through_views" else int(ev[k]))
                   for k in ("see_through_views", "appearance_changed", "edge_excess") if k in ev}
            if "local_recheck" in ev:
                out["local_recheck"] = {k: round(float(v), 3) for k, v in ev["local_recheck"].items()}
            if "clip_guess" in ev:
                out["clip_guess"] = ev["clip_guess"]
            return out
        e["evidence"] = _ev(r) if ch.target is None else {"from": _ev(r), "to": _ev(ch.target)}
        if ch.target is not None:
            t = ch.target
            e["to_box"] = {"center": np.round(t.box_center, 3).tolist(), "size": np.round(t.dims, 3).tolist(),
                           "yaw_deg": round(t.yaw, 1)}
            e["displacement_m"] = np.round(ch.displacement, 3).tolist()
            e["rotation_deg"] = ch.rotation
        data["changes"].append(e)
        e["confident"] = bool(ch.confident)
        if ch.confident:
            lines.append(f"{ch.id}. **{ch.kind.capitalize()}** (confidence {ch.confidence:.2f}): {ch.description}")
    weak = [c for c in changes if not c.confident]
    if weak:
        lines += ["", "## Possible changes (low confidence)", "",
                  "Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.", ""]
        lines += [f"{c.id}. {c.kind.capitalize()} (confidence {c.confidence:.2f}): {c.description}" for c in weak]
    if summary.get("suppressed"):
        lines += ["", "## Suppressed candidates", "",
                  "Regions that changed geometrically but look like bare wall, floor or shadow, "
                  "usually small alignment or lighting errors:", ""]
        lines += [f"* {s}" for s in summary["suppressed"]]
    rej = summary.get("rejected_by_filters") or []
    if rej:
        from collections import Counter
        big = [r for r in rej if r["points"] >= 100]
        lines += ["", "## Rejected by geometric filters", "",
                  f"{len(rej)} candidate regions were dropped before labelling. Every one is listed with "
                  "its reason in `report.json` (`rejected_by_filters`). Counts by reason:", ""]
        lines += [f"* {n} x {why}" for why, n in Counter(r["filter"] for r in rej).most_common()]
        if big:
            lines += ["", "The larger ones (100 points or more):", ""]
            lines += [f"* {r['scan']}: region at {r['center']}, {r['points']} points: {r['filter']}"
                      + (f" ({r['detail']})" if r["detail"] else "") for r in big]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
