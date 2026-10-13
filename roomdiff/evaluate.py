"""Score detections on the synthetic room against its ground truth."""
from __future__ import annotations

import numpy as np

from .backends.synthetic import GROUND_TRUTH, UNOBSERVED_UNCHANGED
from .changes import UNOBSERVED


def _to_room(p, meta, T_room_recon):
    T0_inv, s = meta["world_to_recon"]
    q = T0_inv @ np.r_[p, 1.0]
    q = np.r_[s * q[:3], 1.0]
    return (T_room_recon @ q)[:3]


def evaluate(changes, res, meta, T_room_recon, tol: float = 0.4) -> dict:
    preds = list(changes)
    rows, used = [], set()
    for gt in GROUND_TRUTH:
        hit = None
        for k, c in enumerate(preds):
            if k in used or c.kind != gt["type"]:
                continue
            if gt["type"] == "moved":
                a = _to_room(gt["from"], meta, T_room_recon)
                b = _to_room(gt["to"], meta, T_room_recon)
                ok = (np.linalg.norm(c.region.box_center[:2] - a[:2]) < tol and
                      np.linalg.norm(c.target.box_center[:2] - b[:2]) < tol)
                err = np.linalg.norm((c.target.box_center - c.region.box_center)[:2] - (b - a)[:2])
                zerr = abs(c.target.box_center[2] - b[2])
            else:
                a = _to_room(gt["at"], meta, T_room_recon)
                err = np.linalg.norm(c.region.box_center[:2] - a[:2])
                zerr = abs(c.region.box_center[2] - a[2])
                ok = err < tol
            if ok:
                hit = (k, err, zerr)
                break
        if hit:
            used.add(hit[0])
            c = preds[hit[0]]
            row = {"object": gt["name"], "type": gt["type"], "found": True, "confident": bool(c.confident),
                   "confidence": round(float(c.confidence), 2),
                   # horizontal error of the position (for a move: of the displacement), and the
                   # vertical error of the box centre (for a move: at the new spot)
                   "xy_error_m": round(float(hit[1]), 3), "z_error_m": round(float(hit[2]), 3)}
            if gt["type"] == "moved":
                row["true_turn"] = gt.get("turn")
                row["est_turn"] = c.rotation
            rows.append(row)
        else:
            rows.append({"object": gt["name"], "type": gt["type"], "found": False})
    false_pos = [preds[k].description for k in range(len(preds)) if k not in used]

    # the unchanged bin that only 'before' sees must be unobserved, not removed
    traps = []
    p, _ = res.clouds["before"]
    st = res.states["before"]
    for u in UNOBSERVED_UNCHANGED:
        c = _to_room(u["at"], meta, T_room_recon)
        near = np.linalg.norm(p[:, :2] - c[:2], axis=1) < 0.2
        near &= p[:, 2] > 0.05
        flagged = any(np.linalg.norm(x.region.box_center[:2] - c[:2]) < tol for x in preds)
        traps.append({"object": u["name"], "points": int(near.sum()),
                      "unobserved_share": round(float((st[near] == UNOBSERVED).mean()) if near.any() else 0, 3),
                      "wrongly_reported": flagged})
    tp = sum(r["found"] for r in rows)
    tpc = sum(r["found"] and r["confident"] for r in rows)
    n_conf = sum(c.confident for c in preds)
    return {"all_candidates": {"recall": tp / len(GROUND_TRUTH), "precision": tp / max(len(preds), 1)},
            "confident_only": {"recall": tpc / len(GROUND_TRUTH), "precision": tpc / max(n_conf, 1)},
            "per_change": rows, "false_positives": false_pos, "occlusion_traps": traps}
