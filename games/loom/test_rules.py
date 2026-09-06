import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

MOD = load_game_module(Path(__file__).parent)
GAME = MOD.GAME
ROUNDS = MOD.ROUNDS

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


def make_agents(n):
    return [RandomAgent() for _ in range(n)]


def play_out(n, seed):
    game = GAME(n)
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
    return game, s


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), make_agents(n), seed=seed)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    game, s = play_out(n, seed)
    scores = game.scores(s)
    assert len(scores) == n
    for v in scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_mutation(n):
    game = GAME(n)
    rng = __import__("random").Random(42)
    s = game.setup(rng)
    steps_checked = 0
    while not game.is_terminal(s) and steps_checked < 20:
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        s = game.step(s, a, rng)
        steps_checked += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
    s = game.setup(rng)
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = __import__("random").Random(13)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 30:
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    for p in range(n):
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_seven_rounds_and_two_bare_cells(n):
    """The loom is cut after ROUNDS placements, so exactly two cells stay empty."""
    game, s = play_out(n, 99)
    assert s.round == ROUNDS
    for p in range(n):
        filled = [cell for row in s.grids[p] for cell in row if cell is not None]
        assert len(filled) == ROUNDS
        assert len(filled) == 9 - 2
        for cell in filled:
            assert cell[1] is True  # everything is face-up once the loom is cut
        assert s.hands[p] is None  # leftover hidden card is discarded


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_banked_points_never_fall(n, seed):
    """Points are banked on completion; a banked total can only rise."""
    game = GAME(n)
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    prev = list(s.banked)
    while not game.is_terminal(s):
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        assert all(s.banked[p] >= prev[p] for p in range(n))
        prev = list(s.banked)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_banked_equals_completed_threads(n, seed):
    game, s = play_out(n, seed)
    for p in range(n):
        assert s.banked[p] == float(sum(game._thread_values(s, p)))
        # threads through a bare cell are never closed
        closed = sum(1 for x in s.closed[p] if x)
        assert closed <= 5


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_draft_order_favours_the_trailing_player(n):
    """Each round the fewest banked points drafts first."""
    game = GAME(n)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    seen_rounds = set()
    while not game.is_terminal(s):
        if s.round not in seen_rounds and s.turn_index == 0 and s.step_stage == "draw":
            seen_rounds.add(s.round)
            banked_in_order = [s.banked[p] for p in s.order]
            assert banked_in_order == sorted(banked_in_order)
            assert sorted(s.order) == list(range(n))
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
    assert len(seen_rounds) == ROUNDS


def test_thread_score_patterns():
    from gd_cards import Card

    def c(text):
        return Card.parse(text)

    ts = MOD.thread_score
    assert ts((c("7S"), c("7H"), c("7D"))) == 9
    assert ts((c("5H"), c("6H"), c("7H"))) == 8
    assert ts((c("5H"), c("6S"), c("7H"))) == 4
    assert ts((c("2H"), c("6H"), c("9H"))) == 3
    assert ts((c("2H"), c("2S"), c("9H"))) == 1
    assert ts((c("2H"), c("5S"), c("9H"))) == 0
    assert ts((c("QC"), c("KD"), c("AS"))) == 4  # ace high
    assert ts((c("AS"), c("2C"), c("3D"))) == 4  # ace low
    assert ts((c("KD"), c("AS"), c("2C"))) == 0  # no wrap-around


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_winner_is_unique(n):
    result = play_game(GAME(n), make_agents(n), seed=5)
    assert result.error is None
    assert len(result.winners) == 1
