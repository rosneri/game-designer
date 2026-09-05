import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


def _all_states(game, seed, n_players):
    """Play out a random game, yielding (state, is_terminal) pairs as we go."""
    rng = Random(seed)
    s = game.setup(rng)
    yield s
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        yield s


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    game = GAME(n)
    agents = [RandomAgent() for _ in range(n)]
    result = play_game(game, agents, seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    agents = [RandomAgent() for _ in range(n)]
    result = play_game(game, agents, seed=seed)
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = Random(42)
    states = list(_all_states(game, 42, n))
    checked = 0
    for s in states:
        if game.is_terminal(s):
            continue
        legal = game.legal_actions(s)
        for a in legal[:3]:
            before = copy.deepcopy(s)
            game.step(s, a, Random(123))
            assert s == before
            checked += 1
        if checked > 20:
            break
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions(n, seed):
    game = GAME(n)
    for s in _all_states(game, seed, n):
        if game.is_terminal(s):
            continue
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_observe(n, seed):
    game = GAME(n)
    for s in _all_states(game, seed, n):
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_level4_bonus_applied(n):
    """Final scoring adds 4 points per mechanism at level 4; verify consistency
    between raw internal scores and completed mechanisms at game end."""
    game = GAME(n)
    agents = [RandomAgent() for _ in range(n)]
    result = play_game(game, agents, seed=7)
    s = result.final_state
    assert game.is_terminal(s)
    for p in range(n):
        full_mechs = sum(1 for m in s.mechs[p].values() if len(m) == 4)
        # internal integer score must be >= 4*full_mechs (bonus already added in)
        assert s.scores[p] >= 4 * full_mechs


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_stockroom_capacity(n):
    """Stockroom never exceeds the max of 2 cards for any player, at any point."""
    game = GAME(n)
    for s in _all_states(game, 5, n):
        for stock in s.stocks:
            assert len(stock) <= 2
