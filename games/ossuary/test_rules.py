"""Pytest tests for the Ossuary game package."""
from __future__ import annotations

import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [0, 1, 2]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), [RandomAgent() for _ in range(n)], seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed)
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for x in scores:
        assert isinstance(x, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    checked = 0
    steps = 0
    while not game.is_terminal(s) and steps < 60:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        checked += 1
        s = game.step(s, a, Random(steps))
        steps += 1
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 200:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = Random(123)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 100:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_total_turns_and_final_bell(n):
    """Game should always run exactly total_turns turns and produce final points."""
    game = GAME(n)
    rng = Random(99)
    s = game.setup(rng)
    expected_total = s.total_turns
    steps = 0
    while not game.is_terminal(s) and steps < expected_total + 5:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    assert s.turn == expected_total
    assert game.is_terminal(s)
    assert all(isinstance(x, int) for x in s.points)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_unknown_action_raises(n):
    game = GAME(n)
    rng = Random(5)
    s = game.setup(rng)
    with pytest.raises(ValueError):
        game.step(s, ("frobnicate",), rng)
