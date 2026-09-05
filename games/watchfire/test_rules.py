"""Tests for the Watchfire game package."""
from __future__ import annotations

import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (1, 2, 3)


def _random_agents(n):
    return [RandomAgent() for _ in range(n)]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    game = GAME(n)
    result = play_game(game, _random_agents(n), seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, _random_agents(n), seed=seed)
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    for _ in range(10):
        legal = game.legal_actions(s)
        if not legal:
            break
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        step_rng = Random(rng.randrange(1_000_000))
        game.step(s, a, step_rng)
        assert s == before
        s = game.step(s, a, Random(step_rng.randrange(1_000_000)) if False else step_rng)
        # advance using a fresh rng seeded identically as the mutation check above
        break_now = game.is_terminal(s)
        if break_now:
            break


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions_along_playout(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_observe(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 50:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_exactly_48_turns(n, seed):
    game = GAME(n)
    result = play_game(game, _random_agents(n), seed=seed)
    assert game.is_terminal(result.final_state)
    assert result.final_state.turn == 48


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_beacon_bonus_scoring(n, seed):
    game = GAME(n)
    result = play_game(game, _random_agents(n), seed=seed)
    s = result.final_state
    per_brazier = 10 * n / 4.0
    scores = game.scores(s)
    for p in range(n):
        keeper = s.roles[p] == "keeper"
        favourable = sum(
            1
            for top in s.braziers.values()
            if (top is not None and _rank(top) >= 10) == keeper
        )
        expected_base = sum(_rank(c) for c in s.stashes[p]) + favourable * per_brazier
        assert scores[p] >= expected_base
        assert scores[p] < expected_base + 1
    if game._beacon_lit(s):
        for p in range(n):
            if s.roles[p] == "keeper":
                assert scores[p] >= sum(_rank(c) for c in s.stashes[p]) + 10 * n


def _rank(c: str) -> int:
    head = c[:-1]
    if head == "A":
        return 1
    if head == "Q":
        return 11
    if head == "K":
        return 12
    return int(head)
