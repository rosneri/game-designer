import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [1, 2, 3]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), [RandomAgent() for _ in range(n)], seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed, max_turns=2000)
    assert result.error is None
    scores = result.scores
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    for _ in range(50):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        before = copy.deepcopy(s)
        a = legal[rng.randrange(len(legal))]
        step_rng = __import__("random").Random(rng.randrange(1 << 30))
        game.step(s, a, step_rng)
        assert s == before
        s = game.step(s, a, __import__("random").Random(step_rng.random()))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
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
    rng = __import__("random").Random(11)
    s = game.setup(rng)
    for _ in range(200):
        if game.is_terminal(s):
            break
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_haul_no_duplicate_ranks(n):
    """A player's Haul never holds two cards of the same rank."""
    game = GAME(n)
    rng = __import__("random").Random(99)
    s = game.setup(rng)
    for _ in range(500):
        if game.is_terminal(s):
            break
        for haul in s.hauls:
            ranks = [c.rank for c in haul]
            assert len(ranks) == len(set(ranks))
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_final_round_no_draw(n):
    """Once final_round is set, draw is never a legal action."""
    game = GAME(n)
    rng = __import__("random").Random(123)
    s = game.setup(rng)
    for _ in range(2000):
        if game.is_terminal(s):
            break
        if s.final_round:
            legal = game.legal_actions(s)
            assert ("draw",) not in legal
        legal = game.legal_actions(s)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
