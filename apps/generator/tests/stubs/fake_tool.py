"""Fake `runner`/`pytest`.

GD_FAKE_FAIL="validate:1,gauntlet:99" fails the first N calls of that command; "pytest:=2" fails only call
number 2, which is how a repair that breaks a previously green suite is simulated.
Call counts persist in $GD_FAKE_STATE/<cmd>.count."""
import json
import os
import sys
from pathlib import Path

cmd = sys.argv[1] if len(sys.argv) > 1 else "pytest"
if cmd not in ("validate", "gauntlet", "sim", "play", "gate", "trace"):
    cmd = "pytest"  # pytest is invoked with the game dir as first argument
state = Path(os.environ.get("GD_FAKE_STATE", "/tmp/gd_fake_state"))
state.mkdir(parents=True, exist_ok=True)
cf = state / f"{cmd}.count"
n = int(cf.read_text()) + 1 if cf.exists() else 1
cf.write_text(str(n))
limits = dict(kv.split(":") for kv in os.environ.get("GD_FAKE_FAIL", "").split(",") if kv)
spec = limits.get(cmd, "0")
fail = n == int(spec[1:]) if spec.startswith("=") else n <= int(spec)
if cmd == "gauntlet" and "--json" in sys.argv:
    data = {"passed": not fail, "stages": {"s3_balance": {"passed": not fail, "reason": "seat 0 wins 80%",
            "metrics": {"seat_win": [0.8, 0.2]}}, "s2_playable": {"passed": True}}}
    Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(data))
if cmd == "trace" and not fail:
    print("# stub-duel - 2 players, seats: greedy, random, seed 1\nt1    P0 greedy ('play', 7) options=5 scores=[0.0, 0.0]")
    sys.exit(0)
if fail:
    print(f"{cmd} FAILED: AssertionError: fake failure #{n}", file=sys.stderr)
    sys.exit(1)
print(f"{cmd} ok")
