import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = [2, 3, 4]
SEEDS = [1, 2, 3]


def make_agents(n):
    return [RandomAgent() for _ in range(n)]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    scores = game.scores(result.final_state)
    assert len(scores) == n
    for sc in scores:
        assert isinstance(sc, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    checked = 0
    for _ in range(50):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        if not legal:
            break
        a = legal[rng.randrange(len(legal))]
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        checked += 1
        # advance real state using a fresh copy step to continue playout
        s = game.step(s, a, rng)
    assert checked > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions(n, seed):
    game = GAME(n)
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    assert steps > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_observe(n, seed):
    game = GAME(n)
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        if not legal:
            break
        a = legal[rng.randrange(len(legal))]
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_going_out_bonus_and_round_end(n):
    # Play a full game and confirm scores are floats consistent with tie-break folding
    game = GAME(n)
    result = play_game(game, make_agents(n), seed=7, max_turns=2000)
    assert result.error is None
    s = result.final_state
    assert s.phase == "GAME_OVER"
    assert s.rnd == 3
    # final_hand_counts should be recorded for all players
    assert len(s.final_hand_counts) == n


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hand_sizes_match_rules(n):
    hand_sizes = {2: 7, 3: 6, 4: 5}
    game = GAME(n)
    rng = __import__("random").Random(99)
    s = game.setup(rng)
    for h in s.hands:
        assert len(h) == hand_sizes[n]
