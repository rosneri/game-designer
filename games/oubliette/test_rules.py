import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n_players, seed):
    game = GAME(n_players)
    agents = [RandomAgent() for _ in range(n_players)]
    result = play_game(game, agents, seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n_players, seed):
    game = GAME(n_players)
    agents = [RandomAgent() for _ in range(n_players)]
    result = play_game(game, agents, seed=seed, max_turns=2000)
    scores = game.scores(result.final_state)
    assert len(scores) == n_players
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_no_mutation(n_players):
    game = GAME(n_players)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 50:
        legal = game.legal_actions(s)
        assert legal
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_legal_actions_along_playout(n_players):
    game = GAME(n_players)
    rng = __import__("random").Random(7)
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


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_observe(n_players):
    game = GAME(n_players)
    rng = __import__("random").Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 100:
        for p in range(n_players):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n_players):
        obs = game.observe(s, p)
        assert obs is not None


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_hand_limit_never_exceeded(n_players):
    game = GAME(n_players)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        for hand in s.hands:
            assert len(hand) <= 6
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_scars_reduce_score(n_players):
    # a lair with a scar should score exactly 3 less than the same lair without it
    game = GAME(n_players)
    rng = __import__("random").Random(0)
    s = game.setup(rng)
    s.lairs[0].scars = 0
    base = game._score(s, 0)
    s.lairs[0].scars = 1
    scarred = game._score(s, 0)
    assert base - scarred == 3
