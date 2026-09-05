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
    for _ in range(20):
        if game.is_terminal(s):
            break
        before = copy.deepcopy(s)
        actions = game.legal_actions(s)
        a = rng.choice(actions)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        actions = game.legal_actions(s)
        assert len(actions) > 0
        for a in actions:
            hash(a)
        a = rng.choice(actions)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = __import__("random").Random(99)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 100:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        actions = game.legal_actions(s)
        a = rng.choice(actions)
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_pass_only_when_hand_empty_and_no_sell(n):
    """A player should never be forced to 'pass' while holding cards or a legal sell."""
    game = GAME(n)
    rng = __import__("random").Random(5)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        actions = game.legal_actions(s)
        p = s.turn
        if actions == [("pass",)]:
            assert len(s.hands[p]) == 0
            assert not any(
                s.portfolio[p][su] > 0 and s.market[su] for su in range(4)
            )
        a = rng.choice(actions)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_bell_bonus_only_valid_suit(n):
    """Closing bell die roll must be 0 (unset) or 1-6, and bonus only applies for 1-4."""
    game = GAME(n)
    for seed in SEEDS:
        seen = []
        result = play_game(
            game,
            [RandomAgent() for _ in range(n)],
            seed=seed,
            max_turns=2000,
            on_turn=lambda st, p, a: seen.append(st),
        )
        assert result.error is None
        final_state = seen[-1]
        assert final_state.bell == 0 or 1 <= final_state.bell <= 6
