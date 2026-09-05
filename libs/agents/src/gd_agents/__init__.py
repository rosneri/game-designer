"""Baseline agents for skill measurement: Random, Greedy (1-ply), MCTS (flat UCB + random rollouts).

Agents rely on the Game contract that ``step`` returns a new state and never mutates its input.

All agents implement ``act(game, state, legal, rng) -> Action`` and use only ``rng`` for randomness,
so a match is deterministic for a given seed.
"""
from __future__ import annotations

import math
from random import Random

from gd_gamecore import Action, Game, State


def _rank_value(scores: list[float], p: int) -> float:
    """1.0 = sole winner, 0.0 = not a winner, shared wins split."""
    best = max(scores)
    winners = [i for i, v in enumerate(scores) if v == best]
    return 1.0 / len(winners) if p in winners else 0.0


def rollout(game: Game, state: State, rng: Random, max_steps: int = 400) -> list[float]:
    """Play random moves from ``state`` until terminal (or ``max_steps``); return scores."""
    s = state  # Game.step never mutates its input, so no copy is needed
    for _ in range(max_steps):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        if not legal:
            break
        s = game.step(s, rng.choice(legal), rng)
    return list(game.scores(s))


class RandomAgent:
    name = "random"

    def act(self, game: Game, state: State, legal: list[Action], rng: Random) -> Action:
        return rng.choice(legal)


class GreedyAgent:
    """1-ply lookahead: sample ``n_samples`` outcomes of each action, pick the best mean own-score delta.

    Falls back to a random choice when no action changes the score.
    """

    name = "greedy"

    def __init__(self, n_samples: int = 3):
        self.n_samples = n_samples

    def act(self, game: Game, state: State, legal: list[Action], rng: Random) -> Action:
        if len(legal) == 1:
            return legal[0]
        p = game.current_player(state)
        base = game.scores(state)[p]
        order = list(legal)
        rng.shuffle(order)  # random tie-breaking
        best, best_val = None, -math.inf
        any_change = False
        for a in order:
            tot = 0.0
            for _ in range(self.n_samples):
                s2 = game.step(state, a, Random(rng.getrandbits(64)))
                tot += game.scores(s2)[p] - base
            val = tot / self.n_samples
            any_change |= val != 0.0
            if val > best_val:
                best, best_val = a, val
        return best if any_change else rng.choice(legal)


class MCTSAgent:
    """Flat Monte-Carlo search: UCB1 over root actions, uniformly random rollouts to the end.

    Rollouts stop after ``max_rollout`` steps and are valued by current score rank, so cost stays
    bounded on long games. Uses the full state (no hidden-information handling); good enough to
    measure whether skill matters.
    """

    name = "mcts"

    def __init__(self, n_sims: int = 50, c: float = 1.4, max_rollout: int = 40):
        self.n_sims, self.c, self.max_rollout = n_sims, c, max_rollout

    def act(self, game: Game, state: State, legal: list[Action], rng: Random) -> Action:
        if len(legal) == 1:
            return legal[0]
        p = game.current_player(state)
        n = [0] * len(legal)
        w = [0.0] * len(legal)
        for t in range(self.n_sims):
            if t < len(legal):
                i = t
            else:
                lt = math.log(t)
                i = max(range(len(legal)), key=lambda k: w[k] / n[k] + self.c * math.sqrt(lt / n[k]))
            sim_rng = Random(rng.getrandbits(64))
            s2 = game.step(state, legal[i], sim_rng)
            w[i] += _rank_value(rollout(game, s2, sim_rng, self.max_rollout), p)
            n[i] += 1
        best = max(range(len(legal)), key=lambda k: (n[k], w[k]))
        return legal[best]


AGENTS: dict[str, type] = {"random": RandomAgent, "greedy": GreedyAgent, "mcts": MCTSAgent}

__all__ = ["AGENTS", "GreedyAgent", "MCTSAgent", "RandomAgent", "rollout"]
