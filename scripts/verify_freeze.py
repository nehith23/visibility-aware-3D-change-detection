"""Check that the detection code still matches the hashes frozen before the
held-out room recordings were analysed (heldout/FREEZE.json)."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
m = json.loads((root / "heldout" / "FREEZE.json").read_text())
later = {e["file"]: e for e in m.get("post_freeze_changes", [])}
bad = 0
for f, h in sorted(m["sha256"].items()):
    now = hashlib.sha256((root / f).read_bytes()).hexdigest()
    if f in later:
        ok = now == later[f]["sha256"]
        print(f"{'ok ' if ok else 'CHANGED'}  {f}  (edited after the freeze: {later[f]['why']})")
    else:
        ok = now == h
        print(f"{'ok ' if ok else 'CHANGED'}  {f}")
    bad += not ok
print(f"\nfrozen at {m['frozen_at']}: " + ("all files match" if not bad else f"{bad} file(s) differ"))
sys.exit(1 if bad else 0)
