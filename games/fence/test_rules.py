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
    for _ in range(20):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, Random(rng.randrange(1 << 30)))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = Random(7)
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
def test_observe(n):
    game = GAME(n)
    rng = Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
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
def test_stash_awards_half_value_rounded_down(n):
    game = GAME(n)
    rng = Random(3)
    s = game.setup(rng)
    p = game.current_player(s)
    card = s.hands[p][0]
    from math import floor  # noqa: F401

    value = load_game_module(Path(__file__).parent).value

    expected_gain = value(card) // 2
    before_points = s.points[p]
    s2 = game.step(s, ("stash", card), rng)
    # if this seat's commit triggers full resolve, points update immediately;
    # otherwise it stays pending until all have committed.
    if p not in s2.pending:
        assert s2.points[p] == before_points + expected_gain


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_final_state_all_hands_empty(n):
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=0)
    assert result.error is None
    fs = result.final_state
    assert game.is_terminal(fs)
    assert all(len(h) == 0 for h in fs.hands)
