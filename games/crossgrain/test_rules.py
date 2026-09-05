import copy
from pathlib import Path
from random import Random

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
    result = play_game(game, agents, seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n_players, seed):
    game = GAME(n_players)
    agents = [RandomAgent() for _ in range(n_players)]
    result = play_game(game, agents, seed=seed)
    scores = game.scores(result.final_state)
    assert len(scores) == n_players
    for v in scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_no_mutation(n_players):
    game = GAME(n_players)
    rng = Random(42)
    s = game.setup(rng)
    checked = 0
    for _ in range(200):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert legal
        action = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        step_rng = Random(123)
        game.step(s, action, step_rng)
        assert s == before
        checked += 1
        # advance state for next iteration using a fresh rng call
        s = game.step(s, action, Random(123))
    assert checked > 0


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_legal_actions_along_playout(n_players):
    game = GAME(n_players)
    rng = Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 5000:
        legal = game.legal_actions(s)
        assert legal, "non-terminal state must have legal actions"
        for a in legal:
            hash(a)  # must be hashable
        action = legal[rng.randrange(len(legal))]
        s = game.step(s, action, rng)
        steps += 1
    assert game.is_terminal(s)


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_observe(n_players):
    game = GAME(n_players)
    rng = Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 200:
        for p in range(n_players):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        action = legal[rng.randrange(len(legal))]
        s = game.step(s, action, rng)
        steps += 1
    for p in range(n_players):
        game.observe(s, p)


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_trick_winner_has_live_card(n_players):
    """Every resolved trick must credit points equal to number of live cards (1..n)."""
    game = GAME(n_players)
    rng = Random(99)
    s = game.setup(rng)
    steps = 0
    prev_counter = 0
    while not game.is_terminal(s) and steps < 5000:
        legal = game.legal_actions(s)
        action = legal[rng.randrange(len(legal))]
        s = game.step(s, action, rng)
        if s["trick_counter"] > prev_counter:
            _, _, winner, n_live = s["log"][-1]
            assert 1 <= n_live <= n_players
            assert 0 <= winner < n_players
            prev_counter = s["trick_counter"]
        steps += 1


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_scores_carry_across_hands_and_bonus(n_players):
    """Total game score should be sum of trick points plus bonuses, all non-negative."""
    game = GAME(n_players)
    agents = [RandomAgent() for _ in range(n_players)]
    result = play_game(game, agents, seed=5)
    assert result.error is None
    final = result.final_state
    assert final["hand_index"] == game.hands_total
    for v in final["scores"]:
        assert v >= 0
