"""The ablation script must accept the shipped ground-truth file, notes included."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("ablation", ROOT / "scripts" / "ablation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ground_truth_file_parses_with_notes():
    ab = _load()
    spec = json.loads((ROOT / "examples" / "ground_truth.json").read_text())
    assert any(k.startswith("_") for k in spec)           # the file does carry notes
    sc = ab.scenes(spec)
    assert {"corridor_right", "room_A", "room_null"} <= sc.keys()
    assert all(not k.startswith("_") for k in sc)


def test_malformed_scene_is_an_error():
    ab = _load()
    with pytest.raises(ValueError):
        ab.scenes({"_note": "fine", "broken": {"recon": "x.npz"}})


def test_scoring_counts_hits_and_spatial_false_positives():
    import numpy as np
    ab = _load()
    hit, n, fp = ab.score([np.array([0.1, 0.0, 0.3]), np.array([3.0, 3.0, 0.3])], [[0.0, 0.0], [1.0, 1.0]])
    assert (hit, n, fp) == (1, 2, 1)
