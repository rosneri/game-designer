import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


def _play(n, seed):
    return play_game(GAME(n), [RandomAgent() for _ in range(n)], seed=seed, max_turns=2000)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = _play(n, seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    result = _play(n, seed)
    game = GAME(n)
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


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
        if not legal:
            break
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        checked += 1
        s = game.step(s, a, Random(rng.randint(0, 10**6)))
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
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
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = Random(3)
    s = game.setup(rng)
    for _ in range(200):
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        if not legal:
            break
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_prices_start_at_seven(n):
    game = GAME(n)
    rng = Random(0)
    s = game.setup(rng)
    for su in range(4):
        assert game.price(s, su) == 7


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_game_ends_with_empty_hands(n, seed):
    result = _play(n, seed)
    s = result.final_state
    assert all(len(h) == 0 for h in s.hands)
    assert s.done
