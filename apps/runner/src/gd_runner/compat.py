"""Names from sibling libs (gd_agents, gd_gauntlet, gd_report) with local fallbacks.

The fallbacks are minimal and only used when the real library is not importable yet.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from random import Random
from typing import Any

from gd_gamecore import Game, load_game_module, load_spec, play_game


class _RandomAgent:
    name = "random"

    def act(self, game, state, legal, rng):
        return rng.choice(legal)


class _GreedyAgent:
    """One-step lookahead on own score; ties broken randomly."""

    name = "greedy"

    def act(self, game, state, legal, rng):
        p = game.current_player(state)
        best, best_v = [], None
        for a in legal:
            v = game.scores(game.step(copy.deepcopy(state), a, Random(rng.random())))[p]
            if best_v is None or v > best_v:
                best, best_v = [a], v
            elif v == best_v:
                best.append(a)
        return rng.choice(best)


try:  # real agents
    from gd_agents import AGENTS  # type: ignore
except Exception:  # noqa: BLE001
    AGENTS: dict[str, Any] = {"random": _RandomAgent, "greedy": _GreedyAgent}


def make_agent(name: str, **kw):
    """Instantiate an agent by name from AGENTS (accepts classes or factories)."""
    try:
        factory = AGENTS[name]
    except KeyError:
        raise SystemExit(f"unknown agent {name!r}; known: {', '.join(sorted(AGENTS))}") from None
    try:
        return factory(**kw) if kw else factory()
    except TypeError:
        return factory()


class _GauntletResult:
    def __init__(self, stages: list[dict[str, Any]]):
        self.stages = stages
        fails = [s for s in stages if not s["passed"]]
        self.passed = not fails
        self.failed_stage = fails[0]["stage"] if fails else None

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "failed_stage": self.failed_stage, "stages": self.stages}

    def summary(self) -> str:
        lines = [f"{'PASS' if s['passed'] else 'FAIL'} {s['stage']}: {s.get('detail', '')}" for s in self.stages]
        lines.append("GAUNTLET " + ("PASSED" if self.passed else f"FAILED at {self.failed_stage}"))
        return "\n".join(lines)


def _fallback_gauntlet(game_dir, config=None):
    """s0 schema, s1 import+smoke, s2 playable — enough to unblock the CLI."""
    stages: list[dict[str, Any]] = []
    game_dir = Path(game_dir)
    try:
        spec = load_spec(game_dir)
        stages.append({"stage": "s0_schema", "passed": True, "detail": spec.slug})
    except Exception as e:  # noqa: BLE001
        stages.append({"stage": "s0_schema", "passed": False, "detail": f"{type(e).__name__}: {e}"})
        return _GauntletResult(stages)
    try:
        mod = load_game_module(game_dir)
        g = mod.GAME(spec.players_min)
        assert isinstance(g, Game), "GAME does not satisfy the Game protocol"
        stages.append({"stage": "s1_import", "passed": True, "detail": "GAME importable"})
    except Exception as e:  # noqa: BLE001
        stages.append({"stage": "s1_import", "passed": False, "detail": f"{type(e).__name__}: {e}"})
        return _GauntletResult(stages)
    n_games = (config or {}).get("s2_games", 20)
    errors = []
    for n in spec.player_counts:
        for seed in range(n_games):
            r = play_game(mod.GAME(n), [_RandomAgent()] * n, seed)
            if r.error:
                errors.append(f"n={n} seed={seed}: {r.error}")
    stages.append({"stage": "s2_playable", "passed": not errors, "detail": "; ".join(errors[:3]) or f"{n_games} games/count ok"})
    return _GauntletResult(stages)


try:
    from gd_gauntlet import run_gauntlet  # type: ignore
except Exception:  # noqa: BLE001
    run_gauntlet = _fallback_gauntlet


def result_to_dict(res) -> dict[str, Any]:
    """Tolerant conversion for GauntletResult-like objects."""
    if hasattr(res, "to_dict"):
        return res.to_dict()
    return json.loads(json.dumps(getattr(res, "__dict__", {}), default=str))


__all__ = ["AGENTS", "make_agent", "result_to_dict", "run_gauntlet"]
