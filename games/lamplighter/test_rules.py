import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), [RandomAgent() for _ in range(n)], seed=seed)
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
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    for _ in range(20):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert legal
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
    s = game.setup(rng)
    for _ in range(50):
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    for _ in range(30):
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hand_sizes_capped(n):
    # Hands should never exceed HAND (3) cards during the game.
    game = GAME(n)
    rng = __import__("random").Random(11)
    s = game.setup(rng)
    for _ in range(100):
        assert all(len(h) <= 3 for h in s.hands)
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_deck_conservation(n):
    # Total cards across vault, gallery, hands, draw, discard, piles must equal 52.
    game = GAME(n)
    rng = __import__("random").Random(5)
    s = game.setup(rng)
    for _ in range(100):
        total = (
            len(s.vault)
            + sum(1 for v in s.gallery.values() if v is not None)
            + sum(len(h) for h in s.hands)
            + len(s.draw)
            + len(s.discard)
            + sum(len(pile) for pile in s.piles)
        )
        assert total == 52
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
