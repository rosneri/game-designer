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
    for _ in range(200):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert legal
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, Random(rng.randrange(1 << 30)))
        assert s == before
        checked += 1
        # advance actual state for continued play
        s = game.step(s, a, Random(rng.randrange(1 << 30)))
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 2000:
        legal = game.legal_actions(s)
        assert legal
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, Random(rng.randrange(1 << 30)))
        steps += 1
    assert steps > 0


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
        s = game.step(s, a, Random(rng.randrange(1 << 30)))
        steps += 1
    # also check terminal / final state observation
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hostage_hidden_except_warden(n):
    """Only the current Warden should see the actual hostage card value."""
    game = GAME(n)
    rng = Random(99)
    s = game.setup(rng)
    if s.hostage is not None:
        w = game.warden(s)
        for p in range(n):
            obs = game.observe(s, p)
            if p == w:
                assert obs["hostage"] == str(s.hostage) or obs["hostage"] in ("none",)
            else:
                assert obs["hostage"] in ("face-down", "none")


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_game_ends_when_draw_and_hands_empty(n):
    game = GAME(n)
    rng = Random(5)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 2000:
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, Random(rng.randrange(1 << 30)))
        steps += 1
    assert game.is_terminal(s)
    assert not s.draw
    assert not any(s.hands)
