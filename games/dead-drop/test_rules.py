import copy
from pathlib import Path

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
    result = play_game(game, [RandomAgent() for _ in range(n)], seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    states = []
    result = play_game(
        game,
        [RandomAgent() for _ in range(n)],
        seed=seed,
        on_turn=lambda s, p, a: states.append(s),
    )
    assert result.error is None
    final_state = states[-1]
    scores = game.scores(final_state)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    checked = 0
    for _ in range(30):
        if game.is_terminal(s):
            break
        before = copy.deepcopy(s)
        legal = game.legal_actions(s)
        assert legal
        a = RandomAgent().act(game, s, legal, rng)
        game.step(s, a, rng)
        assert s == before
        checked += 1
        # advance state for next iteration using a fresh step (since step doesn't mutate)
        s = game.step(s, a, rng)
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    assert steps > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 100:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        obs = game.observe(s, p)
        assert obs is not None


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_deck_size_matches_rules(n):
    game = GAME(n)
    rng = __import__("random").Random(11)
    s = game.setup(rng)
    expected_deck = 49 - 3 * n
    assert len(s.deck) == expected_deck


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_final_hand_sizes_at_least_two(n):
    game = GAME(n)
    states = []
    result = play_game(
        game,
        [RandomAgent() for _ in range(n)],
        seed=5,
        on_turn=lambda s, p, a: states.append(s),
    )
    assert result.error is None
    final_state = states[-1]
    for hand in final_state.hands:
        assert len(hand) >= 2
