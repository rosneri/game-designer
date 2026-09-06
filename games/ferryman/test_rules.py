import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent
from gd_cards import Card, Suit

MOD = load_game_module(Path(__file__).parent)
GAME = MOD.GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


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
    rng = __import__("random").Random(seed)
    s = game.setup(rng)
    while not game.is_terminal(s):
        p = game.current_player(s)
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
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
        game.step(s, a, copy.deepcopy(rng))
        assert s == before
        s = game.step(s, a, rng)
        steps_checked += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_legal_actions_along_playout(n):
    game = GAME(n)
    rng = __import__("random").Random(7)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 200:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe(n):
    game = GAME(n)
    rng = __import__("random").Random(11)
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
        game.observe(s, p)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe_hides_other_hands(n):
    game = GAME(n)
    rng = __import__("random").Random(13)
    s = game.setup(rng)
    obs = dict(game.observe(s, 0))
    assert obs["hand"] == tuple(str(c) for c in s.hands[0])
    for q in range(1, n):
        assert not any(str(c) in obs["hand"] for c in s.hands[q])


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_hand_limit_never_exceeded(n):
    game = GAME(n)
    rng = __import__("random").Random(5)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        for h in s.hands:
            assert len(h) <= 6
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_dock_size_bounded(n):
    game = GAME(n)
    rng = __import__("random").Random(3)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 300:
        assert len(s.dock) <= 4
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1


def test_ledger_diminishing_returns():
    ledger = MOD.ledger
    assert ledger(()) == 0
    assert ledger((Card(13, Suit.SPADES),)) == 13
    # second card of the same suit pays half, rounded down; the third pays 1
    assert ledger((Card(13, Suit.SPADES), Card(9, Suit.SPADES))) == 13 + 4
    assert ledger((Card(13, Suit.SPADES), Card(9, Suit.SPADES), Card(2, Suit.SPADES))) == 13 + 4 + 1
    # a fresh suit always pays in full
    assert ledger((Card(13, Suit.SPADES), Card(9, Suit.HEARTS))) == 22
    # order of landing does not matter
    assert ledger((Card(4, Suit.CLUBS), Card(10, Suit.CLUBS))) == 10 + 2


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_poach_only_targets_players_who_are_ahead(n):
    game = GAME(n)
    rng = __import__("random").Random(17)
    s = game.setup(rng)
    steps = 0
    seen_poach = False
    while not game.is_terminal(s) and steps < 400:
        for a in game.legal_actions(s):
            if a[0] == "poach":
                seen_poach = True
                q = a[1]
                assert q != s.cur
                assert game.ferry_total(s, q) > game.ferry_total(s, s.cur)
                assert a[2] == str(s.shore[q][-1])  # only the most recent passenger is exposed
        legal = game.legal_actions(s)
        a = RandomAgent().act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    assert seen_poach


def test_poach_moves_the_card_and_costs_a_hand_card():
    game = GAME(3)
    rng = __import__("random").Random(23)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 400:
        poaches = [a for a in game.legal_actions(s) if a[0] == "poach"]
        if poaches:
            a = poaches[0]
            p, q = s.cur, a[1]
            stolen = s.shore[q][-1]
            before_hand, before_toll = len(s.hands[p]), len(s.toll)
            s2 = game.step(s, a, rng)
            assert s2.shore[p][-1] == stolen
            assert len(s2.shore[q]) == len(s.shore[q]) - 1
            assert len(s2.hands[p]) == before_hand - 1
            assert len(s2.toll) == before_toll + 1
            assert s2.dock == s.dock  # the Dock is untouched by a poach
            assert s2.kin == s.kin  # poaching earns no kin points
            return
        legal = game.legal_actions(s)
        s = game.step(s, RandomAgent().act(game, s, legal, rng), rng)
        steps += 1
    pytest.fail("no poach was ever available")


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_start_seat_rotates_each_round(n):
    game = GAME(n)
    rng = __import__("random").Random(29)
    s = game.setup(rng)
    seen = {s.start_seat}
    rounds = s.round_index
    steps = 0
    while not game.is_terminal(s) and steps < 400:
        assert s.cur == (s.start_seat + s.turn_in_round) % n
        legal = game.legal_actions(s)
        s = game.step(s, RandomAgent().act(game, s, legal, rng), rng)
        if s.round_index != rounds:
            rounds = s.round_index
            assert s.start_seat == (rounds - 1) % n
            seen.add(s.start_seat)
        steps += 1
    assert len(seen) == n


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_scores_follow_the_shore_after_a_steal(n):
    """A stolen passenger must move points, not just cards."""
    game = GAME(n)
    rng = __import__("random").Random(31)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 400:
        poaches = [a for a in game.legal_actions(s) if a[0] == "poach"]
        if poaches:
            a = poaches[0]
            p, q = s.cur, a[1]
            before = game.ferry_total(s, q)
            s2 = game.step(s, a, rng)
            assert game.ferry_total(s2, q) < before
            assert game.ferry_total(s2, p) >= game.ferry_total(s, p)
            return
        legal = game.legal_actions(s)
        s = game.step(s, RandomAgent().act(game, s, legal, rng), rng)
        steps += 1
    pytest.fail("no poach was ever available")


def test_each_player_has_one_secret_charter():
    for n in PLAYER_COUNTS:
        game = GAME(n)
        rng = __import__("random").Random(19)
        s = game.setup(rng)
        assert len(s.charters) == n
        # a Charter is not in anyone's hand and not on the Dock
        board = [str(c) for h in s.hands for c in h] + [str(c) for c in s.dock]
        for c in s.charters:
            assert str(c) not in board


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_observe_hides_other_charters(n):
    game = GAME(n)
    rng = __import__("random").Random(37)
    s = game.setup(rng)
    for p in range(n):
        obs = dict(game.observe(s, p))
        assert obs["charter"] == str(s.charters[p])
        # nothing in the observation reveals a rival's Charter card
        blob = repr(obs)
        for q in range(n):
            if q != p and str(s.charters[q]) not in [str(c) for c in s.dock]:
                assert blob.count(str(s.charters[q])) == 0


def test_charter_bonus_pays_per_card_with_a_set_jump():
    cb = MOD.charter_bonus
    ch = Card(4, Suit.SPADES)
    assert cb((), ch) == 0
    assert cb((Card(9, Suit.HEARTS),), ch) == 0
    assert cb((Card(9, Suit.SPADES),), ch) == 2
    assert cb((Card(9, Suit.SPADES), Card(2, Suit.SPADES)), ch) == 4
    # the third card of the Charter suit unlocks the hidden set bonus
    assert cb((Card(9, Suit.SPADES), Card(2, Suit.SPADES), Card(5, Suit.SPADES)), ch) == 12


def test_charter_is_hidden_from_the_public_total_but_scores_at_the_end():
    game = GAME(2)
    rng = __import__("random").Random(41)
    s = game.setup(rng)
    ch = s.charters[0]
    shore = (Card(9, ch.suit), Card(2, ch.suit), Card(5, ch.suit))
    s = __import__("dataclasses").replace(s, shore=(shore, ()), hands=((), ()), over=True)
    public = game.ferry_total(s, 0)
    assert public == MOD.ledger(shore)  # the Charter never shows in the public total
    assert game.scores(s)[0] > public + 12  # ... but it pays 12 at the end, plus the suit majority


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_no_reshuffle_and_the_game_is_one_crossing(n):
    """The deck is never rebuilt: running it out triggers the end within one round."""
    game = GAME(n)
    rng = __import__("random").Random(43)
    s = game.setup(rng)
    steps = 0
    seen_empty_deck = False
    while not game.is_terminal(s) and steps < 300:
        if not s.deck:
            seen_empty_deck = True
            assert s.end_triggered or not s.dock
        legal = game.legal_actions(s)
        s = game.step(s, RandomAgent().act(game, s, legal, rng), rng)
        steps += 1
    assert game.is_terminal(s)
    assert seen_empty_deck or not s.dock
    assert not hasattr(s, "reshuffle_used")
