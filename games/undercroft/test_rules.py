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
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    for _ in range(30):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, Random(rng.randint(0, 10**6)))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    for _ in range(500):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = Random(13)
    s = game.setup(rng)
    for _ in range(500):
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_same_turn_count(n, seed):
    """End trigger ensures every player gets the same number of turns."""
    result = play_game(GAME(n), [RandomAgent() for _ in range(n)], seed=seed)
    assert result.turns % n == 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hand_limit_respected(n):
    game = GAME(n)
    rng = Random(99)
    s = game.setup(rng)
    for _ in range(500):
        for hand in s["hands"]:
            assert len(hand) <= 5
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
