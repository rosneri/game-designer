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
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed, max_turns=5000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed, max_turns=5000)
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
    steps = 0
    while not game.is_terminal(s) and steps < 30:
        legal = game.legal_actions(s)
        assert legal
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        step_rng = Random(rng.randrange(1 << 30))
        game.step(s, a, step_rng)
        assert s == before
        s = game.step(s, a, Random(step_rng.getstate()[1][0] if False else 42))
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions(n, seed):
    game = GAME(n)
    rng = Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 2000:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    assert game.is_terminal(s)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_observe(n, seed):
    game = GAME(n)
    rng = Random(seed)
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
        obs = game.observe(s, p)
        assert obs is not None


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_52_cards_played(n):
    """Exactly 52 cards should be dealt/drawn/played across the whole game."""
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    total = sum(len(h) for h in s.hands) + len(s.pile)
    assert total == 52
    steps = 0
    while not game.is_terminal(s) and steps < 5000:
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    assert game.is_terminal(s)
    total_end = sum(len(h) for h in s.hands) + len(s.pile) + sum(s.tricks_won) * n
    # each trick removes n cards from circulation (set aside), tricks_won sums to trick count
    assert sum(s.hands, []) == [] and s.pile == []


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_die_never_illegal_value(n):
    """Die value must always be one of the six valid faces during play."""
    game = GAME(n)
    rng = Random(3)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 2000:
        assert 1 <= s.die <= 6
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
