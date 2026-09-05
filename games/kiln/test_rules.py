import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [0, 1, 2]


def make_agents(n):
    return [RandomAgent() for _ in range(n)]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=seed, max_turns=2000)
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for v in scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    s = game.setup(rng)
    agent = RandomAgent()
    for _ in range(50):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        if not legal:
            break
        p = game.current_player(s)
        a = agent.act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, Random(1234))
        assert s == before
        s = game.step(s, a, Random(1234))


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
        agent = RandomAgent()
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


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
        if not legal:
            break
        agent = RandomAgent()
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_cabinet_scoring_only_sums_printed_ranks_no_kiln(n):
    """Ware sitting in a kiln at game end should not contribute to score sums beyond
    what's captured by _points; verify each player's raw cabinet-rank sum is <= total score."""
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=99, max_turns=2000)
    s = result.final_state
    scores = game.scores(s)
    for p in range(n):
        cab_sum = sum(c.rank for c in s.cabinet[p])
        # score = cab_sum + suit bonuses (multiples of 5) + tiny tiebreak epsilon
        assert scores[p] >= cab_sum - 1e-3


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_round_cap_respected(n):
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=3, max_turns=5000)
    s = result.final_state
    assert s.round_no <= game.round_cap
