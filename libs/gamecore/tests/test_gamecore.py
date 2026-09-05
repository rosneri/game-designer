
from gd_gamecore import Game, GameSpec, play_game


class HighCard:
    """Trivial game: each player draws a number; highest wins. Used to test the play loop."""

    def __init__(self, n_players=2):
        self.n_players = n_players

    def setup(self, rng):
        return {"turn": 0, "vals": []}

    def current_player(self, s):
        return s["turn"]

    def legal_actions(self, s):
        return ["draw", "pass"]

    def step(self, s, a, rng):
        v = rng.randint(1, 13) if a == "draw" else 0
        return {"turn": s["turn"] + 1, "vals": s["vals"] + [v]}

    def is_terminal(self, s):
        return s["turn"] >= self.n_players

    def scores(self, s):
        return [float(v) for v in s["vals"]]

    def observe(self, s, p):
        return tuple(s["vals"])

    def describe(self, s):
        return str(s)


class Rand:
    def act(self, game, state, legal, rng):
        return rng.choice(legal)


def test_protocol_and_play():
    g = HighCard(3)
    assert isinstance(g, Game)
    r = play_game(g, [Rand()] * 3, seed=1, record=True)
    assert r.error is None and r.turns == 3 and len(r.history) == 3
    assert play_game(g, [Rand()] * 3, seed=1).scores == r.scores


def test_spec_validation():
    s = GameSpec(slug="test-game", name="T", players_min=2, players_max=4)
    assert list(s.player_counts) == [2, 3, 4]
