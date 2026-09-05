"""Runner operations. Pure functions that return data; the CLI does the printing."""
from __future__ import annotations

import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from random import Random
from typing import Any, TextIO

from gd_gamecore import Game, GameSpec, PlayResult, load_game_module, load_spec, play_game
from gd_gm import ScriptedGM

from .compat import make_agent


class ValidationError(Exception):
    """Raised by :func:`validate` with a human-readable, actionable message."""


def make_gm(spec: GameSpec, kind: str = "scripted", seed: int = 0):
    """Return a GM if the spec enables one, else None. ``kind`` is 'scripted' or 'llm'."""
    if not spec.gm.enabled:
        return None
    if kind == "llm":
        from gd_gm import LLMGM

        return LLMGM(spec.gm.role)
    return ScriptedGM(Random(seed))


def build_game(game_dir: str | Path, n_players: int, gm_kind: str = "scripted", seed: int = 0) -> tuple[GameSpec, Game]:
    """Load spec + module and instantiate ``GAME(n_players, gm=...)``."""
    spec = load_spec(game_dir)
    mod = load_game_module(game_dir)
    gm = make_gm(spec, gm_kind, seed)
    game = mod.GAME(n_players, gm=gm) if gm is not None else mod.GAME(n_players)
    return spec, game


# ---------------------------------------------------------------- validate
def validate(game_dir: str | Path, n_games: int = 3, seeds_from: int = 0) -> dict[str, Any]:
    """Fast s0+s1 check. Raises ValidationError with a clear message on the first problem."""
    game_dir = Path(game_dir)
    if not game_dir.is_dir():
        raise ValidationError(f"{game_dir} is not a directory")
    for f in ("spec.json", "rules.py"):
        if not (game_dir / f).exists():
            raise ValidationError(f"missing {game_dir / f}")
    try:
        spec = load_spec(game_dir)
    except Exception as e:
        raise ValidationError(f"spec.json does not validate as GameSpec:\n{e}") from e
    try:
        mod = load_game_module(game_dir)
    except Exception as e:
        raise ValidationError(f"rules.py failed to import: {type(e).__name__}: {e}") from e
    played: dict[int, list[int]] = {}
    for n in spec.player_counts:
        try:
            game = mod.GAME(n, gm=make_gm(spec, "scripted", 0)) if spec.gm.enabled else mod.GAME(n)
        except Exception as e:
            raise ValidationError(f"GAME({n}) failed: {type(e).__name__}: {e} (need __init__(n_players, gm=None))") from e
        if not isinstance(game, Game):
            missing = [m for m in Game.__protocol_attrs__ if not hasattr(game, m)]  # type: ignore[attr-defined]
            raise ValidationError(f"GAME({n}) does not satisfy the Game protocol; missing: {missing}")
        if getattr(game, "n_players", None) != n:
            raise ValidationError(f"GAME({n}).n_players == {getattr(game, 'n_players', None)!r}, expected {n}")
        agents = [make_agent("random")] * n
        for seed in range(seeds_from, seeds_from + n_games):
            r = play_game(game, agents, seed, record=True)
            if r.error:
                last = r.history[-1] if r.history else None
                where = f" (last action: p{last.player} {last.action})" if last else ""
                raise ValidationError(f"random game n={n} seed={seed} failed after {r.turns} turns: {r.error}{where}")
            if r.turns == 0:
                raise ValidationError(f"game n={n} seed={seed} was terminal immediately after setup")
            _check_purity(game, seed)
            played.setdefault(n, []).append(r.turns)
    return {"slug": spec.slug, "name": spec.name, "player_counts": list(spec.player_counts), "turns": played}


def _check_purity(game: Game, seed: int) -> None:
    """step() must not mutate its input; observe/describe must work on a fresh state."""
    import copy

    rng = Random(seed)
    s = game.setup(rng)
    if game.is_terminal(s):
        return
    snap = copy.deepcopy(s)
    a = game.legal_actions(s)[0]
    game.step(s, a, Random(seed))
    if _repr(s) != _repr(snap):
        raise ValidationError(f"step() mutated its input state (action {a!r}); return a new/copied state instead")
    for p in range(game.n_players):
        game.observe(s, p)
    if not isinstance(game.describe(s), str):
        raise ValidationError("describe() must return a str")


def _repr(s: Any) -> str:
    try:
        return repr(s)
    except Exception:  # noqa: BLE001
        return str(id(s))


# ---------------------------------------------------------------- sim
def sim(
    game_dir: str | Path, players: int, games: int, agents: list[str], seed: int = 0, gm_kind: str = "scripted"
) -> dict[str, Any]:
    """Play ``games`` games; agent i sits at seat i (list is cycled to fill seats)."""
    spec, game = build_game(game_dir, players, gm_kind, seed)
    names = [agents[i % len(agents)] for i in range(players)]
    seats = [make_agent(n) for n in names]
    wins = [0.0] * players
    turns: list[int] = []
    draws = errors = 0
    scores = [[] for _ in range(players)]
    for g in range(games):
        r: PlayResult = play_game(game, seats, seed + g)
        if r.error:
            errors += 1
            continue
        turns.append(r.turns)
        if r.is_draw:
            draws += 1
        for w in r.winners:
            wins[w] += 1 / len(r.winners)
        for i, v in enumerate(r.scores):
            scores[i].append(v)
    ok = games - errors
    return {
        "slug": spec.slug,
        "players": players,
        "games": games,
        "errors": errors,
        "seats": [
            {
                "seat": i,
                "agent": names[i],
                "win_rate": round(wins[i] / ok, 4) if ok else None,
                "mean_score": round(statistics.fmean(scores[i]), 3) if scores[i] else None,
            }
            for i in range(players)
        ],
        "by_agent": {
            n: round(sum(wins[i] for i in range(players) if names[i] == n) / ok / names.count(n), 4) if ok else None
            for n in dict.fromkeys(names)
        },
        "draw_rate": round(draws / ok, 4) if ok else None,
        "turns": {
            "mean": round(statistics.fmean(turns), 2) if turns else None,
            "min": min(turns) if turns else None,
            "max": max(turns) if turns else None,
            "stdev": round(statistics.pstdev(turns), 2) if turns else None,
        },
    }


# ---------------------------------------------------------------- play
def play(
    game_dir: str | Path,
    players: int,
    gm_kind: str = "scripted",
    seed: int | None = None,
    input_fn: Callable[[str], str] | None = None,
    out: TextIO | None = None,
    others: str = "greedy",
) -> PlayResult:
    """Interactive game: human at seat 0, ``others`` agents elsewhere. Returns the PlayResult."""
    seed = Random().randrange(1 << 30) if seed is None else seed
    spec, game = build_game(game_dir, players, gm_kind, seed)
    out = out or sys.stdout
    human = _HumanAgent(input_fn or input, out)
    agents = [human] + [make_agent(others) for _ in range(players - 1)]

    def on_turn(s, p, a):
        if p != 0:
            print(f"-- seat {p} plays: {a}", file=out)

    print(f"== {spec.name} — {players} players, seed {seed}. You are seat 0.", file=out)
    r = play_game(game, agents, seed, on_turn=on_turn)
    print("== GAME OVER", file=out)
    if r.error:
        print(f"error: {r.error}", file=out)
    print(f"scores: {r.scores}  winners: {r.winners}", file=out)
    return r


class _HumanAgent:
    def __init__(self, input_fn, out):
        self.input_fn, self.out = input_fn, out

    def act(self, game, state, legal, rng):
        print("\n" + game.describe(state), file=self.out)
        print(f"you see: {game.observe(state, 0)}", file=self.out)
        for i, a in enumerate(legal):
            print(f"  [{i}] {a}", file=self.out)
        while True:
            raw = self.input_fn(f"your move (0-{len(legal) - 1}, q to quit): ").strip()
            if raw.lower() in ("q", "quit"):
                raise KeyboardInterrupt
            if raw.isdigit() and int(raw) < len(legal):
                return legal[int(raw)]
            print("invalid choice", file=self.out)


__all__ = ["ValidationError", "build_game", "make_gm", "play", "sim", "validate"]
