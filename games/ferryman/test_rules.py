import copy
from pathlib import Path

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
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    while not game.is_terminal(s):
        p = game.current_player(s)
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
    scores = game.scores(s)
    assert len(scores) == n
    for v in scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    steps_checked = 0
    while not game.is_terminal(s) and steps_checked < 20:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, copy.deepcopy(rng))
        assert s == before
        s = game.step(s, a, rng)
        steps_checked += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
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
    rng = __import__("random").Random(11)
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
def test_hand_limit_never_exceeded(n):
    game = GAME(n)
    rng = __import__("random").Random(5)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        for h in s.hands:
            assert len(h) <= 6
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_dock_size_bounded(n):
    game = GAME(n)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        assert len(s.dock) <= 4
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
