"""Full pipeline on the synthetic room: every planted change must be found,
nothing else reported, and the corner only 'before' saw must stay unverified."""
from roomdiff.backends.synthetic import generate
from roomdiff.config import Config
from roomdiff.evaluate import evaluate
from roomdiff.pipeline import analyse


def test_synthetic_room(tmp_path):
    scans, meta = generate(tmp_path / "frames", n_frames=20)
    changes, _, room, res = analyse(scans, tmp_path, Config(use_clip=False))
    score = evaluate(changes, res, meta, room["T_room_recon"])
    assert score["all_candidates"]["recall"] == 1.0, score
    assert score["all_candidates"]["precision"] == 1.0, score
    # nothing invented in the confident tier either
    assert score["confident_only"]["precision"] == 1.0, score
    trap = score["occlusion_traps"][0]
    assert not trap["wrongly_reported"]
    assert trap["unobserved_share"] > 0.8
    moved = [r for r in score["per_change"] if r["type"] == "moved"][0]
    assert moved["est_turn"] is not None and abs(abs(moved["est_turn"]) - 90) <= 15
    assert abs(room["scale"] - 1 / 0.37) / (1 / 0.37) < 0.03
    for f in ("scene.html", "topdown.png", "evidence.png", "report.md", "report.json", "changes.ply"):
        assert (tmp_path / f).exists()
