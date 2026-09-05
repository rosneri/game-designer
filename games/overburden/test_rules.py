import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [1, 2, 3]


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
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed)
    assert result.error is None
    scores = result.scores
    assert len(scores) == n
    for v in scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    checked = 0
    for _ in range(50):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = rng.choice(legal)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        checked += 1
        s = game.step(s, a, Random(rng.random()))
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    assert steps > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 200:
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
def test_line_bonus_matches_scores(n):
    """Live line bonuses should be reflected in the current (non-final) scores."""
    game = GAME(n)
    rng = Random(99)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
        if not game.is_terminal(s):
            bonus = game._lines(s)
            scores = game.scores(s)
            for p in range(n):
                assert scores[p] == pytest.approx(s.banked[p] + bonus[p])


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_final_winner_is_unique(n):
    """The tie-break fraction ensures a single winner at game end."""
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=123)
    assert result.error is None
    assert len(result.winners) == 1
