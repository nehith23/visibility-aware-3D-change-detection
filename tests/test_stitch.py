"""Multi-pass reconstruction: passes come back in unrelated similarity frames
(as VGGT's do) and must be stitched into one consistent scene."""
import numpy as np
from scipy.spatial.transform import Rotation

from roomdiff.backends.stitch import plan_passes, stitched_forward, umeyama
from roomdiff.backends.synthetic import generate
from roomdiff.config import Config
from roomdiff.evaluate import evaluate
from roomdiff.pipeline import analyse
from roomdiff.scene import Frame, Scan


def test_plan_passes_covers_everything_once_plus_anchors():
    passes, anchors = plan_passes(40, 40, 28)
    assert all(len(p) <= 28 for p in passes)
    seen = set().union(*map(set, passes))
    assert seen == set(range(80))
    for p in passes:
        assert set(anchors) <= set(p)
    assert plan_passes(10, 10, 28) == ([list(range(20))], [])


def test_umeyama_recovers_similarity():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    R = Rotation.from_euler("xyz", [10, -20, 35], degrees=True).as_matrix()
    y = 2.5 * x @ R.T + [1, 2, 3]
    s, R2, t = umeyama(x, y)
    assert abs(s - 2.5) < 1e-6 and np.allclose(R2, R, atol=1e-6) and np.allclose(t, [1, 2, 3], atol=1e-6)


def _fake_vggt(frames, rng, noise=0.004):
    """forward(sel) that returns true geometry in a fresh random similarity
    frame per call, with multiplicative depth noise."""
    def forward(sel):
        s = rng.uniform(0.3, 3.0)
        R = Rotation.random(random_state=rng.integers(1 << 31)).as_matrix()
        t = rng.normal(size=3)
        S = np.eye(4)
        S[:3, :3], S[:3, 3] = s * R, t
        extr, intr, depth, conf = [], [], [], []
        for i in sel:
            f = frames[i]
            T = np.eye(4)
            T[:3, :3] = R @ f.T_wc[:3, :3]
            T[:3, 3] = S[:3, :3] @ f.T_wc[:3, 3] + t
            extr.append(np.linalg.inv(T)[:3, :])
            intr.append(f.K)
            depth.append(f.depth * s * (1 + rng.normal(0, noise, f.depth.shape)))
            conf.append(1 + 1 / np.maximum(f.depth, 0.1))   # smooth, nearer = more confident
        return np.stack(extr), np.stack(intr), np.stack(depth), np.stack(conf)
    return forward


def test_stitched_synthetic_room_still_scores_perfectly(tmp_path):
    rng = np.random.default_rng(3)
    scans, meta = generate(tmp_path / "frames", n_frames=24)
    frames = scans[0].frames + scans[1].frames
    valid = np.stack([np.ones(f.hw, bool) for f in frames])
    T_wc, K, depth, conf, info = stitched_forward(24, 24, 20, valid, _fake_vggt(frames, rng))
    assert info["passes"] >= 3
    assert all(st["residual_rel"] < 0.02 for st in info["stitch"])
    stitched = [Frame(f.image, depth[i].astype(np.float32), conf[i], K[i], T_wc[i], f.full_path)
                for i, f in enumerate(frames)]
    # every camera must sit where the truth says, up to one global similarity
    true_c = np.stack([f.T_wc[:3, 3] for f in frames])
    s, R, t = umeyama(T_wc[:, :3, 3], true_c)
    err = np.linalg.norm(T_wc[:, :3, 3] @ (s * R).T + t - true_c, axis=1)
    assert err.max() < 0.01 * np.ptp(true_c, axis=0).max()
    # map back into the evaluator's frame, then the full pipeline must still score 4/4
    fixed = []
    for f in stitched:
        T = np.eye(4)
        T[:3, :3] = R @ f.T_wc[:3, :3]
        T[:3, 3] = s * R @ f.T_wc[:3, 3] + t
        f.T_wc, f.depth = T, (f.depth * s).astype(np.float32)
        fixed.append(f)
    out = [Scan("before", fixed[:24]), Scan("after", fixed[24:])]
    changes, _, room, res = analyse(out, tmp_path / "out", Config(use_clip=False))
    score = evaluate(changes, res, meta, room["T_room_recon"])
    assert score["all_candidates"]["recall"] == 1.0 and score["all_candidates"]["precision"] == 1.0, score
