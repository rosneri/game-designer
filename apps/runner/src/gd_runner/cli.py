"""``runner`` console script: gauntlet | sim | play | validate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compat import result_to_dict, run_gauntlet
from .core import ValidationError, play, sim, trace, trace_text, validate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runner", description="Run, test and play game packages.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gauntlet", help="run the deterministic gauntlet; exit 1 on failure")
    g.add_argument("game_dir")
    g.add_argument("--json", dest="out", default=None, help="stages JSON path (default <game_dir>/gauntlet.json)")

    s = sub.add_parser("sim", help="simulate games between agents; prints JSON stats")
    s.add_argument("game_dir")
    s.add_argument("--players", type=int, required=True)
    s.add_argument("--games", type=int, default=100)
    s.add_argument("--agents", default="random", help="comma list, one per seat (cycled), e.g. random,greedy")
    s.add_argument("--seed", type=int, default=0)

    pl = sub.add_parser("play", help="play interactively as seat 0 against greedy agents")
    pl.add_argument("game_dir")
    pl.add_argument("--players", type=int, required=True)
    pl.add_argument("--gm", choices=["llm", "scripted"], default="scripted")
    pl.add_argument("--seed", type=int, default=None)

    tr = sub.add_parser("trace", help="print one readable game transcript (turns, actions, running scores)")
    tr.add_argument("game_dir")
    tr.add_argument("--players", type=int, required=True)
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--agents", default="greedy,random", help="comma list, one per seat (cycled)")
    tr.add_argument("--head", type=int, default=25, help="turns to show from the start")
    tr.add_argument("--tail", type=int, default=15, help="turns to show from the end")

    v = sub.add_parser("validate", help="fast check: spec loads, module imports, 3 random games")
    v.add_argument("game_dir")
    v.add_argument("--games", type=int, default=3)
    return p


def cmd_gauntlet(a) -> int:
    res = run_gauntlet(a.game_dir)
    out = Path(a.out) if a.out else Path(a.game_dir) / "gauntlet.json"
    out.write_text(json.dumps(result_to_dict(res), indent=2, default=str))
    print(res.summary())
    print(f"wrote {out}")
    return 0 if res.passed else 1


def cmd_sim(a) -> int:
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    print(json.dumps(sim(a.game_dir, a.players, a.games, agents, a.seed), indent=2))
    return 0


def cmd_play(a) -> int:
    try:
        play(a.game_dir, a.players, gm_kind=a.gm, seed=a.seed)
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
    return 0


def cmd_trace(a) -> int:
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    t = trace(a.game_dir, a.players, seed=a.seed, agents=agents, head=a.head, tail=a.tail)
    print(trace_text(t))
    return 1 if t["error"] else 0


def cmd_validate(a) -> int:
    try:
        info = validate(a.game_dir, n_games=a.games)
    except ValidationError as e:
        print(f"INVALID {a.game_dir}\n{e}", file=sys.stderr)
        return 1
    turns = ", ".join(f"{n}p: {t}" for n, t in info["turns"].items())
    print(f"OK {info['slug']} ({info['name']}) players={info['player_counts']} turns per game: {turns}")
    return 0


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    code = {"gauntlet": cmd_gauntlet, "sim": cmd_sim, "play": cmd_play, "trace": cmd_trace,
            "validate": cmd_validate}[a.cmd](a)
    if argv is None:
        sys.exit(code)
    return code


if __name__ == "__main__":
    main()
