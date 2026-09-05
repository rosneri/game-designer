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
    assert result.error is None
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for s in scores:
        assert isinstance(s, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    checked = 0
    for _ in range(30):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, Random(rng.randrange(1 << 30)))
        assert s == before
        checked += 1
        s = game.step(s, a, Random(rng.randrange(1 << 30)))
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_nonempty_and_hashable(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 200:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    assert steps > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 100:
        for p in range(n):
            game.observe(s, p)
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_deck_depth_matches_rules(n):
    depth = {2: 30, 3: 33, 4: 36}[n]
    game = GAME(n)
    rng = Random(3)
    s = game.setup(rng)
    # after setup, one reveal already consumed from the sealed depth
    assert len(s.deck) == depth - 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hall_limit_never_exceeded(n):
    game = GAME(n)
    rng = Random(5)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        assert len(s.hall) <= 6
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    assert len(s.hall) <= 6
