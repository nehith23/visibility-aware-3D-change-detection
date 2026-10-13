import numpy as np
import pytest

from roomdiff.changes import GONE, PRESENT, UNOBSERVED, DepthIndex, Region, classify
from roomdiff.config import Config
from roomdiff.geometry import backproject, estimate_down, fit_floor, project, voxel_downsample
from roomdiff.scene import Frame, Scan


def _frame(depth_value=2.0, w=64, h=48, T=None):
    K = np.array([[50.0, 0, w / 2], [0, 50.0, h / 2], [0, 0, 1]])
    d = np.full((h, w), depth_value, np.float32)
    return Frame(np.zeros((h, w, 3), np.uint8), d, np.ones_like(d), K, np.eye(4) if T is None else T)


def test_backproject_project_roundtrip():
    f = _frame()
    T = np.eye(4)
    T[:3, 3] = [0.3, -0.2, 0.1]
    f.T_wc = T
    p, _, uv = backproject(f)
    u, v, z = project(p, f)
    assert np.allclose(u, uv[:, 0] + .5, atol=1e-4)
    assert np.allclose(v, uv[:, 1] + .5, atol=1e-4)
    assert np.allclose(z, 2.0, atol=1e-5)


def test_voxel_downsample_averages():
    p = np.array([[0.001, 0, 0], [0.009, 0, 0], [0.5, 0, 0]])
    c = np.array([[0, 0, 0], [100, 100, 100], [50, 50, 50]], float)
    q, cc = voxel_downsample(p, c, size=0.02)
    assert len(q) == 2
    assert np.allclose(sorted(cc[:, 0]), [50, 50])


def test_visibility_three_states():
    """A camera looking at a wall 2 m away:
    a point at 1 m on its ray is see-through (gone),
    a point at 2 m is present, a point behind the wall is occluded,
    a point outside the view is unobserved."""
    cfg = Config(window=3, min_votes=1)
    idx = DepthIndex(Scan("x", [_frame(2.0)]), cfg)
    pts = np.array([[0, 0, 1.0], [0, 0, 2.0], [0, 0, 3.5], [10, 0, 2.0]])
    agree, through, _, _ = idx.votes(pts)
    st = classify(agree, through, cfg)
    assert st[0] == GONE
    assert st[1] == PRESENT
    assert st[2] == UNOBSERVED          # occluded = no evidence
    assert st[3] == UNOBSERVED          # out of view


def test_floor_and_gravity():
    rng = np.random.default_rng(0)
    floor = np.c_[rng.uniform(-2, 2, 5000), rng.uniform(-2, 2, 5000), np.zeros(5000)]
    clutter = np.c_[rng.uniform(-1, 1, 1000), rng.uniform(-1, 1, 1000), rng.uniform(0.2, 1.5, 1000)]
    pts = np.r_[floor, clutter]
    up, c, ratio = fit_floor(pts, np.array([0.05, 0.0, -1.0]) / np.linalg.norm([0.05, 0, -1]))
    assert up[2] > 0.999
    assert abs(c) < 0.01
    assert ratio > 0.5


def test_estimate_down_from_upright_cameras():
    # camera looking along +y with world z up: image down (cam +y) = world -z
    T = np.eye(4)
    T[:3, :3] = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    down = estimate_down([Scan("a", [_frame(T=T)])])
    assert np.allclose(down, [0, 0, -1])


def test_region_footprint_contains_own_points():
    rng = np.random.default_rng(1)
    t = np.deg2rad(30)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    xy = (rng.uniform(-1, 1, (500, 2)) * [0.4, 0.15]) @ R.T + [1, 2]
    pts = np.c_[xy, rng.uniform(0.1, 0.6, 500)]
    r = Region("before", pts, np.full((500, 3), 120.0))
    assert r.footprint_mask(pts, 0.01).mean() > 0.99
    assert r.dims[0] == pytest.approx(0.8, abs=0.05)
    assert r.dims[1] == pytest.approx(0.3, abs=0.05)


def test_cache_roundtrip_relative_paths(tmp_path):
    from PIL import Image
    from roomdiff.scene import load_scans, save_scans
    (tmp_path / "frames").mkdir()
    img = tmp_path / "frames" / "0000.jpg"
    Image.new("RGB", (64, 48)).save(img)
    f = _frame(1.5)
    f.full_path = str(img)
    save_scans(tmp_path / "recon.npz", [Scan("before", [f]), Scan("after", [f])])
    moved = tmp_path.parent / (tmp_path.name + "_moved")
    tmp_path.rename(moved)
    sc = load_scans(moved / "recon.npz")
    assert sc[0].frames[0].full_path == str(moved / "frames" / "0000.jpg")
    assert np.allclose(sc[0].frames[0].depth, 1.5, atol=1e-3)


def test_plan_prefers_landscape_budget():
    from unittest import mock
    import roomdiff.backends.vggt_backend as vb
    with mock.patch.object(vb, "gpu_memory_gb", return_value=(12.0, "test")):
        same = vb.plan([(1920, 1080)], [(1920, 1080)])
        mixed = vb.plan([(1920, 1080)], [(1080, 1920)])
    assert same["max_side"] == 518 and same["frames_per_video"] >= 18
    assert mixed["mixed_orientation"] and mixed["canvas"][0] == mixed["canvas"][1]


def test_portrait_frames_go_on_a_square_canvas(tmp_path):
    from PIL import Image
    import roomdiff.backends.vggt_backend as vb
    paths = []
    for i in range(2):
        p = tmp_path / f"{i}.jpg"
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(p)
        paths.append(p)
    imgs, valid, affine = vb._prepare(paths, 518)
    assert imgs.shape[1:3] == (518, 518)
    ys, xs = np.nonzero(valid[0])
    sx, ox, sy, oy = affine[0]
    assert abs(xs.min() * sx + ox) < 1 and abs((xs.max() + 1) * sx + ox - 1080) < 4
    assert abs(ys.min() * sy + oy) < 1 and abs((ys.max() + 1) * sy + oy - 1920) < 4
    assert (imgs[0][~valid[0]] == 255).all()
