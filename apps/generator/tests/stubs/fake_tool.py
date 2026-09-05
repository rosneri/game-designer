"""Fake `runner`/`pytest`. GD_FAKE_FAIL="validate:1,gauntlet:99" = fail first N calls of that command.
Call counts persist in $GD_FAKE_STATE/<cmd>.count."""
import json
import os
import sys
from pathlib import Path

cmd = sys.argv[1] if len(sys.argv) > 1 else "pytest"
if cmd not in ("validate", "gauntlet", "sim", "play", "gate"):
    cmd = "pytest"  # pytest is invoked with the game dir as first argument
state = Path(os.environ.get("GD_FAKE_STATE", "/tmp/gd_fake_state"))
state.mkdir(parents=True, exist_ok=True)
cf = state / f"{cmd}.count"
n = int(cf.read_text()) + 1 if cf.exists() else 1
cf.write_text(str(n))
limits = dict(kv.split(":") for kv in os.environ.get("GD_FAKE_FAIL", "").split(",") if kv)
fail = n <= int(limits.get(cmd, 0))
if cmd == "gauntlet" and "--json" in sys.argv:
    data = {"passed": not fail, "stages": {"s3_balance": {"passed": not fail, "reason": "seat 0 wins 80%",
            "metrics": {"seat_win": [0.8, 0.2]}}, "s2_playable": {"passed": True}}}
    Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(data))
if fail:
    print(f"{cmd} FAILED: AssertionError: fake failure #{n}", file=sys.stderr)
    sys.exit(1)
print(f"{cmd} ok")
