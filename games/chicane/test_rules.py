import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [1, 2, 3]


def make_game(n):
    return GAME(n)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    game = make_game(n)
    agents = [RandomAgent() for _ in range(n)]
    result = play_game(game, agents, seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = make_game(n)
    agents = [RandomAgent() for _ in range(n)]
    result = play_game(game, agents, seed=seed, max_turns=2000)
    assert result.error is None
    final_state = result.history[-1][0] if result.history else None
    # get final state via play_game history if available, else re-derive
    scores = result.scores
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = make_game(n)
    rng = Random(42)
    s = game.setup(rng)
    for _ in range(20):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = legal[0]
        before = copy.deepcopy(s)
        step_rng = Random(123)
        game.step(s, a, step_rng)
        assert s == before
        # advance state using a fresh rng for actual progression
        adv_rng = Random(99)
        s = game.step(s, a, adv_rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = make_game(n)
    rng = Random(7)
    s = game.setup(rng)
    agent = RandomAgent()
    for _ in range(200):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for act in legal:
            hash(act)  # must be hashable
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = make_game(n)
    rng = Random(11)
    s = game.setup(rng)
    agent = RandomAgent()
    for _ in range(50):
        if game.is_terminal(s):
            break
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hand_limit_never_exceeded(n):
    game = make_game(n)
    rng = Random(5)
    s = game.setup(rng)
    agent = RandomAgent()
    for _ in range(300):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
        for hand in s.hands:
            assert len(hand) <= 7


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_track_never_exceeds_length(n):
    game = make_game(n)
    rng = Random(6)
    s = game.setup(rng)
    agent = RandomAgent()
    for _ in range(300):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
        assert len(s.track) <= s.length
