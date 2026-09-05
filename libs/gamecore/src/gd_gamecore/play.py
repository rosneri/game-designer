from __future__ import annotations

import copy
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from types import ModuleType
from typing import Any, Protocol

from .game import Action, Game, State


class AgentLike(Protocol):
    def act(self, game: Game, state: State, legal: list[Action], rng: Random) -> Action: ...


@dataclass
class TurnRecord:
    player: int
    n_legal: int
    action: str


@dataclass
class PlayResult:
    scores: list[float]
    turns: int
    winners: list[int]
    history: list[TurnRecord] = field(default_factory=list)
    error: str | None = None
    final_state: Any = None  # last state reached (terminal unless ``error`` is set)

    @property
    def is_draw(self) -> bool:
        return len(self.winners) != 1


def play_game(
    game: Game,
    agents: list[AgentLike],
    seed: int,
    max_turns: int = 2000,
    record: bool = False,
    on_turn: Callable[[State, int, Action], None] | None = None,
) -> PlayResult:
    """Run one game to completion. Deterministic for (game, agents, seed)."""
    rng = Random(seed)
    agent_rng = Random(seed ^ 0x5EED)
    s = game.setup(rng)
    hist: list[TurnRecord] = []
    turns = 0
    try:
        while not game.is_terminal(s):
            if turns >= max_turns:
                return PlayResult(game.scores(s), turns, [], hist, error=f"exceeded max_turns={max_turns}", final_state=s)
            p = game.current_player(s)
            legal = game.legal_actions(s)
            if not legal:
                return PlayResult(game.scores(s), turns, [], hist, error="no legal actions in non-terminal state", final_state=s)
            a = agents[p].act(game, s, legal, agent_rng)
            if a not in legal:
                return PlayResult(game.scores(s), turns, [], hist, error=f"agent chose illegal action {a!r}", final_state=s)
            before = copy.deepcopy(s) if record else None
            s = game.step(s, a, rng)
            if record:
                hist.append(TurnRecord(p, len(legal), str(a)))
                del before
            if on_turn:
                on_turn(s, p, a)
            turns += 1
        sc = game.scores(s)
        if len(sc) != game.n_players:
            return PlayResult(sc, turns, [], hist, error="scores length != n_players", final_state=s)
        best = max(sc)
        winners = [i for i, v in enumerate(sc) if v == best]
        return PlayResult(sc, turns, winners, hist, final_state=s)
    except Exception as e:  # noqa: BLE001
        return PlayResult([0.0] * game.n_players, turns, [], hist, error=f"{type(e).__name__}: {e}", final_state=s)


def load_game_module(game_dir: str | Path) -> ModuleType:
    """Import ``<game_dir>/rules.py`` as an isolated module and return it (exposes GAME)."""
    game_dir = Path(game_dir)
    path = game_dir / "rules.py"
    name = f"gd_game_{game_dir.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "GAME"):
        raise AttributeError("rules.py must define GAME")
    return mod
