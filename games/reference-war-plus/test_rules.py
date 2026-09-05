from pathlib import Path
from random import Random

from gd_gamecore import Game, load_game_module, load_spec, play_game

HERE = Path(__file__).parent


class Rand:
    def act(self, game, state, legal, rng):
        return rng.choice(legal)


def test_spec_and_protocol():
    spec = load_spec(HERE)
    assert spec.slug == "reference-war-plus" and spec.components.jokers == 2
    game = load_game_module(HERE).GAME(3)
    assert isinstance(game, Game) and game.n_players == 3


def test_second_deal_uses_rng_and_carries_points():
    g = load_game_module(HERE).GAME(2)
    seen = set()
    for seed in range(3):
        r = play_game(g, [Rand()] * 2, seed, record=True)
        assert r.error is None and r.turns == 108
        seen.add(tuple(r.scores))
    assert len(seen) > 1


def test_random_games_terminate_and_are_deterministic():
    GAME = load_game_module(HERE).GAME
    for n in (2, 3, 4):
        g = GAME(n)
        for seed in range(10):
            r = play_game(g, [Rand()] * n, seed, record=True)
            assert r.error is None, r.error
            assert r.turns == 2 * (54 - 54 % n)  # two deals; every non-discarded card is played once
            assert abs(sum(r.scores)) <= 2 * 54 * 15  # bounded by total card strength
        assert play_game(g, [Rand()] * n, 3).scores == play_game(g, [Rand()] * n, 3).scores


def test_hidden_information_and_purity():
    g = load_game_module(HERE).GAME(2)
    s = g.setup(Random(1))
    a = g.legal_actions(s)[0]
    s2 = g.step(s, a, Random(1))
    assert s.played == () and len(s2.played) == 1  # input not mutated
    hand0, n_down, *_ = g.observe(s2, 1)
    assert n_down == 1 and str(a) not in hand0  # seat 1 sees a card is down, not which


def test_joker_beats_ace_prices_and_ties_pool():
    from gd_cards import Card

    g = load_game_module(HERE).GAME(2)
    S = type(g.setup(Random(0)))
    base = S(((Card(1, 0),), (Card(0, 0),)), (), 0, (), (0, 0), 0, 0)
    s1 = g.step(g.step(base, Card(1, 0), Random(0)), Card(0, 0), Random(0))
    # seat 0 pays 7 (A); seat 1 pays 8 (joker) and collects 14; joker winner commits last -> leader 0
    assert s1.points == (-7, 6) and s1.leader == 0 and g.is_terminal(s1)
    tie = S(((Card(9, 0), Card(2, 1)), (Card(9, 1), Card(3, 2))), (), 0, (), (0, 0), 0, 0)
    t1 = g.step(g.step(tie, Card(9, 0), Random(0)), Card(9, 1), Random(0))
    assert t1.pot == 9 and t1.points == (-5, -5) and t1.leader == 0
    t2 = g.step(g.step(t1, Card(2, 1), Random(0)), Card(3, 2), Random(0))
    assert t2.points == (-6, -5 - 2 + 2 + 9) and t2.pot == 0 and t2.leader == 0


def test_greedy_prefers_cheapest_winner():
    from gd_cards import Card

    g = load_game_module(HERE).GAME(2)
    S = type(g.setup(Random(0)))
    s = S(((Card(4, 0),), (Card(5, 1), Card(13, 2))), (), 0, (), (0, 0), 0, 0)
    s = g.step(s, Card(4, 0), Random(0))
    win_cheap = g.step(s, Card(5, 1), Random(0)).points[1]
    win_dear = g.step(s, Card(13, 2), Random(0)).points[1]
    assert win_cheap > win_dear
