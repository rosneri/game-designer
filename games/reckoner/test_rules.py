"""Pytest tests for the Reckoner game package."""
from __future__ import annotations

import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
    scores = game.scores(s)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_mutation(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 30:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, Random(seed + steps))
        assert s == before
        s = game.step(s, a, Random(seed + steps))
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions_along_playout(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 60:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_observe(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 30:
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
def test_exactly_48_plays(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
    assert s.plays == 48


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_field_empty_requires_trail(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    # empty out the field manually to check legal actions only offer trail
    empty_field_state = s.__class__(**{**s.__dict__, "field": ()})
    legal = game.legal_actions(empty_field_state)
    assert len(legal) > 0
    assert all(a[0] == "trail" for a in legal)
