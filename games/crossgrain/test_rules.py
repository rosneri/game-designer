import copy
from pathlib import Path
from random import Random

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

MOD = load_game_module(Path(__file__).parent)
GAME = MOD.GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)
HONOURS = ("J", "Q", "K", "A")


def card_value(card, pledge):
    base = 3 if card[:-1] in HONOURS else 1
    return base * 2 if card[-1] == pledge else base


def finish_pledges(game, s, rng):
    while s["phase"] == "pledge":
        legal = game.legal_actions(s)
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
    return s


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
        game.step(s, action, Random(123))
        assert s == before
        checked += 1
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
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
        steps += 1
    assert game.is_terminal(s)


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_observe_hides_other_pledges(n_players):
    game = GAME(n_players)
    rng = Random(11)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 400:
        for p in range(n_players):
            obs = game.observe(s, p)
            assert obs is not None
            assert obs["my_pledge"] == s["pledges"][p]
            for q, shown in enumerate(obs["pledges"]):
                if q != p and s["pledges"][q] is not None:
                    assert shown == "?"
            assert obs["hand"] == tuple(s["hands"][p])
        legal = game.legal_actions(s)
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
        steps += 1


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_pledge_phase_opens_every_deal(n_players):
    """Every seat pledges a suit it holds before any card of a deal is played."""
    game = GAME(n_players)
    rng = Random(3)
    s = game.setup(rng)
    deals_seen = 0
    while not game.is_terminal(s):
        assert s["phase"] == "pledge"
        assert all(x is None for x in s["pledges"])
        for p in range(n_players):
            assert s["turn"] == p
            legal = game.legal_actions(s)
            assert legal and all(a[0] == "pledge" for a in legal)
            held = {c[-1] for c in s["hands"][p]}
            assert all(a[1] in held for a in legal)
            s = game.step(s, legal[rng.randrange(len(legal))], rng)
        assert s["phase"] == "play"
        assert all(x is not None for x in s["pledges"])
        assert s["turn"] == s["leader"]
        deals_seen += 1
        while s["phase"] == "play":
            legal = game.legal_actions(s)
            s = game.step(s, legal[rng.randrange(len(legal))], rng)
    assert deals_seen == game.deals_total


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_trick_winner_harvests_live_cards(n_players):
    """Each resolved trick credits 1..n live cards, all of one suit, to the winner."""
    game = GAME(n_players)
    rng = Random(99)
    s = game.setup(rng)
    steps = 0
    prev_counter = 0
    prev_harvest = [0] * n_players
    while not game.is_terminal(s) and steps < 5000:
        legal = game.legal_actions(s)
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
        if s["trick_counter"] > prev_counter:
            _, suit, winner, n_live = s["log"][-1]
            assert 1 <= n_live <= n_players
            assert 0 <= winner < n_players
            if s["phase"] == "play":  # harvest is cleared when a deal is scored
                gained = len(s["harvest"][winner]) - prev_harvest[winner]
                assert gained == n_live
                assert all(c[-1] == suit for c in s["harvest"][winner][-n_live:])
            prev_harvest = [len(h) for h in s["harvest"]]
            prev_counter = s["trick_counter"]
        steps += 1
    assert s["trick_counter"] == s["tricks_total"]


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_trick_pays_token_width_and_harvest_at_once(n_players):
    """Over one trick the winner gains 2 (token) + width + harvest, everyone else 0."""
    game = GAME(n_players)
    rng = Random(23)
    s = game.setup(rng)
    seen_grain_trick = False
    at_trick_start = list(s["scores"])
    while not game.is_terminal(s):
        if s["phase"] == "play" and not s["current_trick"]:
            at_trick_start = list(s["scores"])
        prev_counter = s["trick_counter"]
        legal = game.legal_actions(s)
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
        if s["phase"] == "play" and s["trick_counter"] > prev_counter:
            _, suit, winner, n_live = s["log"][-1]
            pledge = s["pledges"][winner]
            cards = s["harvest"][winner][-n_live:]
            harvest_pts = sum(card_value(c, pledge) for c in cards)
            if pledge == suit:
                seen_grain_trick = True
                assert harvest_pts == 2 * sum(card_value(c, None) for c in cards)
            for p in range(n_players):
                gain = s["scores"][p] - at_trick_start[p]
                if p == winner:
                    assert gain == 2 + (n_live - 1) + harvest_pts
                else:
                    assert gain == 0
    assert seen_grain_trick


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_end_of_deal_bonuses(n_players):
    """Sheaf pays 3 for an honour of your suit, blight costs 2 for no card of it."""
    game = GAME(n_players)
    agents = [RandomAgent() for _ in range(n_players)]
    result = play_game(game, agents, seed=5)
    assert result.error is None
    final = result.final_state
    assert final["phase"] == "game_over"
    assert sum(final["tricks_won"]) == final["tricks_total"]
    assert final["deal_index"] == game.deals_total
    for p in range(n_players):
        pledge = final["pledges"][p]
        mine = [c for c in final["harvest"][p] if c[-1] == pledge]
        bonus = game.harvest_bonus(final, p)
        if not mine:
            assert bonus == -2
        elif any(c[:-1] in HONOURS for c in mine):
            assert bonus == 3
        else:
            assert bonus == 0
        assert game.harvest_value(final, p) == sum(
            card_value(c, pledge) for c in final["harvest"][p]
        )
    order = game.ranking(final)
    assert sorted(order) == list(range(n_players))
    assert final["scores"][order[0]] == max(final["scores"])


@pytest.mark.parametrize("n_players", PLAYER_COUNTS)
def test_game_length(n_players):
    """Fixed length: one pledge per seat per deal plus one turn per card."""
    game = GAME(n_players)
    rng = Random(17)
    s = game.setup(rng)
    assert all(len(h) == game.hand_size for h in s["hands"])
    assert s["tricks_total"] == game.hand_size * game.deals_total
    steps = 0
    while not game.is_terminal(s) and steps < 2000:
        legal = game.legal_actions(s)
        s = game.step(s, legal[rng.randrange(len(legal))], rng)
        steps += 1
    assert steps == game.deals_total * (n_players + n_players * game.hand_size)
