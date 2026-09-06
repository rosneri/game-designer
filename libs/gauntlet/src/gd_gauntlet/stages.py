"""Gauntlet stages s0..s8. Each stage is ``fn(ctx) -> StageResult``. Pure except for reading spec files."""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from statistics import mean
from typing import Any

from gd_agents import GreedyAgent, MCTSAgent, RandomAgent
from gd_gamecore import Game, GameSpec, PlayResult, load_game_module, load_spec, play_game
from gd_gm import ScriptedGM

from .config import GauntletConfig


@dataclass
class StageResult:
    name: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "metrics": self.metrics,
                "reason": self.reason, "seconds": round(self.seconds, 3)}


@dataclass
class Context:
    """Shared state between stages (later stages reuse games recorded by earlier ones)."""

    game_dir: Path
    cfg: GauntletConfig
    spec: GameSpec | None = None
    game_cls: type | None = None
    random_games: dict[int, list[PlayResult]] = field(default_factory=dict)  # n_players -> results

    def make_game(self, n: int, seed: int) -> Game:
        assert self.game_cls is not None and self.spec is not None
        if self.spec.gm.enabled:
            return self.game_cls(n, gm=ScriptedGM(Random(seed)))
        return self.game_cls(n)

    def counts(self) -> list[int]:
        assert self.spec is not None
        return list(self.spec.player_counts)


def _fail(name: str, reason: str, **metrics: Any) -> StageResult:
    return StageResult(name, False, metrics, reason)


def _ok(name: str, **metrics: Any) -> StageResult:
    return StageResult(name, True, metrics)


def _shared_wins(results: list[PlayResult], n: int) -> list[float]:
    """Per-seat win counts with draws split equally between winners."""
    w = [0.0] * n
    for r in results:
        for p in r.winners:
            w[p] += 1.0 / len(r.winners)
    return w


def _run_matches(ctx: Context, n: int, agents_for: Callable[[int], list], k: int, tag: int,
                 record: bool = False) -> list[PlayResult]:
    out = []
    for i in range(k):
        seed = ctx.cfg.seed * 1_000_003 + tag * 10_007 + n * 101 + i
        g = ctx.make_game(n, seed)
        out.append(play_game(g, agents_for(i), seed, max_turns=ctx.cfg.max_turns, record=record))
    return out


# ---------------------------------------------------------------- stages

def s0_schema(ctx: Context) -> StageResult:
    p = ctx.game_dir / "spec.json"
    if not p.is_file():
        return _fail("s0_schema", "spec.json missing")
    try:
        spec = load_spec(p)
    except Exception as e:  # noqa: BLE001
        return _fail("s0_schema", f"spec.json invalid: {type(e).__name__}: {e}")
    if spec.components.jokers > 2 or spec.components.dice > 2:
        return _fail("s0_schema", "components out of range (jokers<=2, dice<=2)")
    ctx.spec = spec
    return _ok("s0_schema", slug=spec.slug, players=[spec.players_min, spec.players_max],
               jokers=spec.components.jokers, dice=spec.components.dice)


def s1_import(ctx: Context) -> StageResult:
    try:
        mod = load_game_module(ctx.game_dir)
    except Exception as e:  # noqa: BLE001
        return _fail("s1_import", f"import failed: {type(e).__name__}: {e}")
    ctx.game_cls = mod.GAME
    for n in ctx.counts():
        try:
            g = ctx.make_game(n, 0)
        except Exception as e:  # noqa: BLE001
            return _fail("s1_import", f"GAME({n}) failed: {type(e).__name__}: {e}")
        if not isinstance(g, Game):
            return _fail("s1_import", f"GAME({n}) does not satisfy the Game protocol")
        if g.n_players != n:
            return _fail("s1_import", f"GAME({n}).n_players == {g.n_players}")
        for seed in range(ctx.cfg.smoke_seeds):
            try:
                s = g.setup(Random(seed))
                if g.is_terminal(s):
                    return _fail("s1_import", f"setup() is already terminal (n={n}, seed={seed})")
                legal = g.legal_actions(s)
                if not legal:
                    return _fail("s1_import", f"no legal actions after setup (n={n}, seed={seed})")
                g.observe(s, g.current_player(s))
                g.describe(s)
            except Exception as e:  # noqa: BLE001
                return _fail("s1_import", f"smoke failed (n={n}, seed={seed}): {type(e).__name__}: {e}")
    return _ok("s1_import", player_counts=ctx.counts())


def s2_playable(ctx: Context) -> StageResult:
    metrics: dict[str, Any] = {}
    errors: list[str] = []
    for n in ctx.counts():
        res = _run_matches(ctx, n, lambda i, n=n: [RandomAgent()] * n, ctx.cfg.playable_games, tag=2, record=True)
        ctx.random_games[n] = res
        errs = [r.error for r in res if r.error]
        turns = [r.turns for r in res]
        metrics[f"p{n}"] = {"mean_turns": round(mean(turns), 1), "max_turns": max(turns),
                            "error_rate": len(errs) / len(res)}
        errors += [f"n={n}: {e}" for e in errs[:3]]
    if errors:
        return _fail("s2_playable", "; ".join(errors), **metrics)
    return _ok("s2_playable", **metrics)


def s3_balance(ctx: Context) -> StageResult:
    metrics: dict[str, Any] = {}
    reasons = []
    for n in ctx.counts():
        res = _run_matches(ctx, n, lambda i, n=n: [RandomAgent()] * n, ctx.cfg.balance_games, tag=3)
        ok = [r for r in res if not r.error]
        if len(ok) < len(res):
            reasons.append(f"n={n}: {len(res) - len(ok)} errored games")
        if not ok:
            continue
        rates = [round(w / len(ok), 3) for w in _shared_wins(ok, n)]
        draws = sum(r.is_draw for r in ok) / len(ok)
        metrics[f"p{n}"] = {"seat_win_rates": rates, "draw_rate": round(draws, 3)}
        lo, hi = 1 / n - ctx.cfg.seat_tolerance, 1 / n + ctx.cfg.seat_tolerance
        bad = [i for i, r in enumerate(rates) if not lo <= r <= hi]
        if bad:
            reasons.append(f"n={n}: seats {bad} outside [{lo:.2f}, {hi:.2f}] ({rates})")
        if draws >= ctx.cfg.max_draw_rate:
            reasons.append(f"n={n}: draw rate {draws:.2f} >= {ctx.cfg.max_draw_rate}")
    return StageResult("s3_balance", not reasons, metrics, "; ".join(reasons))


def dominance(rate: float, n: int) -> float:
    """Greedy's edge over random on a per-player-count scale: 0.0 = random-level, 1.0 = wins every game."""
    base = 1 / n
    return (rate - base) / (1 - base)


def s4_skill(ctx: Context) -> StageResult:
    metrics: dict[str, Any] = {}
    reasons = []
    rates: list[float] = []
    doms: list[float] = []

    def hero_rate(n: int, hero, k: int, tag: int) -> float | None:
        def agents(i: int) -> list:
            a: list = [RandomAgent()] * n
            a[i % n] = hero
            return a
        res = _run_matches(ctx, n, agents, k, tag=tag)
        ok = [(r, i % n) for i, r in enumerate(res) if not r.error]
        if not ok:
            return None
        return sum((seat in r.winners) / len(r.winners) for r, seat in ok) / len(ok)

    for n in ctx.counts():
        rate = hero_rate(n, GreedyAgent(ctx.cfg.greedy_samples), ctx.cfg.skill_games, tag=4)
        metrics[f"p{n}"] = {"greedy_win_rate": None if rate is None else round(rate, 3)}
        if rate is None:
            reasons.append(f"n={n}: all greedy games errored")
            continue
        need = 1 / n + ctx.cfg.skill_margin
        if rate <= need:
            reasons.append(f"n={n}: greedy win rate {rate:.2f} <= {need:.2f} (no skill)")
        rates.append(rate)
        d = dominance(rate, n)
        metrics[f"p{n}"]["dominance"] = round(d, 3)
        doms.append(d)
    # Luck check: the greedy agent sees the full state (it can peek at hidden info), so a
    # perfect record at 2 players is common in hidden-information games. We only require that
    # luck shows up at SOME player count.
    if rates and min(rates) >= ctx.cfg.skill_max_winrate:
        reasons.append(f"greedy win rate >= {ctx.cfg.skill_max_winrate} at every player count (no luck)")
    # Dominance check: a 1-ply "grab the most points right now" bot should NOT crush random play at
    # every seat count. When it does, the game is a scoring treadmill with no counterplay.
    if doms:
        md = mean(doms)
        metrics["skill_dominance"] = round(md, 3)
        if md > ctx.cfg.max_skill_dominance:
            reasons.append(
                f"greedy dominance {md:.2f} > {ctx.cfg.max_skill_dominance} (per-count {[round(x, 2) for x in doms]}): "
                "a 1-ply score-greedy bot beats random almost always, so the game rewards no planning. "
                "Add counterplay against the leader, delayed/hidden scoring, or costs that make the "
                "immediate-points action wrong sometimes")
    if ctx.cfg.mcts_games > 0:
        n0 = ctx.counts()[0]
        mr = hero_rate(n0, MCTSAgent(ctx.cfg.mcts_sims, max_rollout=ctx.cfg.mcts_rollout), ctx.cfg.mcts_games, tag=44)
        metrics[f"p{n0}"]["mcts_win_rate"] = None if mr is None else round(mr, 3)
    return StageResult("s4_skill", not reasons, metrics, "; ".join(reasons))


def s5_decisions(ctx: Context) -> StageResult:
    turns = [t for res in ctx.random_games.values() for r in res for t in r.history]
    if not turns:
        return _fail("s5_decisions", "no recorded turns (s2 did not run?)")
    mean_legal = mean(t.n_legal for t in turns)
    forced = sum(t.n_legal == 1 for t in turns) / len(turns)
    metrics = {"mean_legal_actions": round(mean_legal, 2), "forced_share": round(forced, 3),
               "turns_sampled": len(turns)}
    reasons = []
    if mean_legal < ctx.cfg.min_mean_legal:
        reasons.append(f"mean legal actions {mean_legal:.2f} < {ctx.cfg.min_mean_legal}")
    if forced > ctx.cfg.max_forced_share:
        reasons.append(f"forced-move share {forced:.2f} > {ctx.cfg.max_forced_share}")
    return StageResult("s5_decisions", not reasons, metrics, "; ".join(reasons))


def s6_length(ctx: Context) -> StageResult:
    metrics: dict[str, Any] = {}
    reasons = []
    means = []
    # Seconds per turn grow with the number of options a player must weigh.
    turns_all = [t for res in ctx.random_games.values() for r in res for t in r.history]
    mean_legal = mean(t.n_legal for t in turns_all) if turns_all else 2.0
    mpt = ctx.cfg.minutes_per_turn * (1 + math.log2(max(mean_legal, 1.0)))
    metrics["minutes_per_turn"] = round(mpt, 3)
    for n, res in ctx.random_games.items():
        ok = [r.turns for r in res if not r.error]
        if not ok:
            continue
        m = mean(ok)
        means.append(m)
        metrics[f"p{n}"] = {"mean_turns": round(m, 1), "est_minutes": round(m * mpt, 1)}
        if not ctx.cfg.turns_min <= m <= ctx.cfg.turns_max:
            reasons.append(f"n={n}: mean turns {m:.0f} outside [{ctx.cfg.turns_min}, {ctx.cfg.turns_max}]")
    if not means:
        return _fail("s6_length", "no completed random games")
    lo, hi = min(means) * mpt, max(means) * mpt
    blo, bhi = ctx.cfg.minutes_band
    metrics["est_minutes_range"] = [round(lo, 1), round(hi, 1)]
    if hi < blo or lo > bhi:
        reasons.append(f"estimated {lo:.0f}-{hi:.0f} min does not overlap [{blo:.0f}, {bhi:.0f}]")
    return StageResult("s6_length", not reasons, metrics, "; ".join(reasons))


def _leaders(scores: list[float]) -> frozenset[int]:
    top = max(scores)
    return frozenset(i for i, v in enumerate(scores) if v == top)


def tension_of(trace: list[list[float]]) -> dict[str, float] | None:
    """How long the outcome stayed open, from one game's per-turn score trace.

    ``lead_changes``: how often the set of leaders changed.
    ``decided_at``: fraction of the game elapsed when the winner took the lead for the last time; 0.9 means
    the winner was still catchable almost to the end, 0.1 means a runaway leader.
    ``comeback``: the winner was not leading at the three-quarter mark.
    """
    if len(trace) < 4:
        return None
    winner = _leaders(trace[-1])
    changes = sum(1 for i in range(1, len(trace)) if _leaders(trace[i]) != _leaders(trace[i - 1]))
    behind = [i for i, sc in enumerate(trace) if not (_leaders(sc) & winner)]
    decided = (max(behind) + 1) / len(trace) if behind else 0.0
    return {"lead_changes": float(changes), "decided_at": decided,
            "comeback": float(not (_leaders(trace[int(len(trace) * 0.75)]) & winner))}


def s8_tension(ctx: Context) -> StageResult:
    """Was the winner ever in doubt? A game nobody can catch up in is balanced but not fun."""
    per_count: dict[str, Any] = {}
    lead_changes, decided_at, comebacks = [], [], []
    for n in ctx.counts():
        samples = []
        for i in range(ctx.cfg.tension_games):
            # greedy seats mixed with random ones: a plausible table, not a coin-flip one
            agents = [GreedyAgent() if p % 2 == 0 else RandomAgent() for p in range(n)]
            r = play_game(ctx.make_game(n, ctx.cfg.seed + i), agents, seed=ctx.cfg.seed + i,
                          max_turns=ctx.cfg.max_turns, record_scores=True)
            if r.error:
                continue
            t = tension_of(r.score_trace)
            if t:
                samples.append(t)
        if not samples:
            continue
        per_count[f"p{n}"] = {k: round(mean(s[k] for s in samples), 3) for k in ("lead_changes", "decided_at", "comeback")}
        lead_changes.append(per_count[f"p{n}"]["lead_changes"])
        decided_at.append(per_count[f"p{n}"]["decided_at"])
        comebacks.append(per_count[f"p{n}"]["comeback"])
    if not lead_changes:
        return _fail("s8_tension", "no completed games to measure", **per_count)
    metrics = {**per_count, "mean_lead_changes": round(mean(lead_changes), 2),
               "mean_decided_at": round(mean(decided_at), 3), "mean_comeback_rate": round(mean(comebacks), 3)}
    reasons = []
    if metrics["mean_lead_changes"] < ctx.cfg.min_lead_changes:
        reasons.append(f"only {metrics['mean_lead_changes']} lead changes per game "
                       f"(< {ctx.cfg.min_lead_changes}): the standings barely move, so play has little drama. "
                       "Add ways to catch the leader, swing scoring, or points that land late")
    if metrics["mean_decided_at"] < ctx.cfg.min_decided_at:
        reasons.append(f"the winner takes the final lead {metrics['mean_decided_at']:.0%} into the game "
                       f"(< {ctx.cfg.min_decided_at:.0%}): an early leader is never caught. "
                       "Delay or hide some scoring, or give trailing players a real lever")
    return _fail("s8_tension", "; ".join(reasons), **metrics) if reasons else _ok("s8_tension", **metrics)


def fingerprint(spec: GameSpec) -> frozenset[str]:
    c = spec.components
    return frozenset({*(f"mech:{m.strip().lower()}" for m in spec.mechanics),
                      f"jokers:{c.jokers}", f"dice:{c.dice}", f"full_deck:{c.uses_full_deck}",
                      *(f"extra:{e.strip().lower()}" for e in c.extra),
                      f"gm:{spec.gm.enabled}", f"hidden:{spec.hidden_information}", f"order:{spec.turn_order}"})


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def s7_novelty(ctx: Context) -> StageResult:
    assert ctx.spec is not None
    me = fingerprint(ctx.spec)
    nearest, best = None, -1.0
    for other in sorted(ctx.game_dir.parent.glob("*/spec.json")):
        if other.parent.resolve() == ctx.game_dir.resolve():
            continue
        try:
            o = load_spec(other)
        except Exception:  # noqa: BLE001, S112  (broken sibling specs are not this game's problem)
            continue
        if o.slug == ctx.spec.slug:
            continue
        sim = jaccard(me, fingerprint(o))
        if sim > best:
            nearest, best = o.slug, sim
    metrics = {"fingerprint": sorted(me), "nearest": nearest, "similarity": round(max(best, 0.0), 3)}
    if nearest is not None and best >= ctx.cfg.max_novelty_similarity:
        return _fail("s7_novelty", f"too similar to {nearest} (jaccard {best:.2f})", **metrics)
    return _ok("s7_novelty", **metrics)


STAGES: list[Callable[[Context], StageResult]] = [
    s0_schema, s1_import, s2_playable, s3_balance, s4_skill, s5_decisions, s6_length, s7_novelty, s8_tension,
]


def run_stage(fn: Callable[[Context], StageResult], ctx: Context) -> StageResult:
    t0 = time.perf_counter()
    try:
        res = fn(ctx)
    except Exception as e:  # noqa: BLE001
        res = _fail(fn.__name__, f"stage crashed: {type(e).__name__}: {e}")
    res.seconds = time.perf_counter() - t0
    return res


__all__ = ["STAGES", "Context", "StageResult", "dominance", "fingerprint", "jaccard", "run_stage"]
