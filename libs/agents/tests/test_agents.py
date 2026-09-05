from random import Random

from gd_agents import AGENTS, GreedyAgent, MCTSAgent, RandomAgent
from gd_gamecore import play_game


class PickHigh:
    """Each player, in turn, picks one of 3 hidden values for `rounds` rounds; sum wins. Greedy should win."""

    def __init__(self, n_players=2, rounds=5):
        self.n_players, self.rounds = n_players, rounds

    def setup(self, rng):
        return {"turn": 0, "score": [0.0] * self.n_players, "hand": [rng.randint(1, 13) for _ in range(3)]}

    def current_player(self, s):
        return s["turn"] % self.n_players

    def legal_actions(self, s):
        return [0, 1, 2]

    def step(self, s, a, rng):
        p = self.current_player(s)
        sc = list(s["score"])
        sc[p] += s["hand"][a] + rng.randint(1, 6)
        return {"turn": s["turn"] + 1, "score": sc, "hand": [rng.randint(1, 13) for _ in range(3)]}

    def is_terminal(self, s):
        return s["turn"] >= self.rounds * self.n_players

    def scores(self, s):
        return s["score"]

    def observe(self, s, p):
        return tuple(s["score"])

    def describe(self, s):
        return str(s)


def _winrate(agent, n=60):
    g = PickHigh(2)
    wins = 0.0
    for seed in range(n):
        r = play_game(g, [agent, RandomAgent()], seed)
        assert r.error is None
        wins += (0 in r.winners) / len(r.winners)
    return wins / n


def test_registry():
    assert set(AGENTS) == {"random", "greedy", "mcts"}
    for cls in AGENTS.values():
        assert callable(cls().act)


def test_random_is_legal_and_deterministic():
    g = PickHigh(3)
    a, b = play_game(g, [RandomAgent()] * 3, 7), play_game(g, [RandomAgent()] * 3, 7)
    assert a.error is None and a.scores == b.scores


def test_greedy_beats_random():
    assert _winrate(GreedyAgent()) > 0.7


def test_mcts_beats_random():
    assert _winrate(MCTSAgent(n_sims=20), n=30) > 0.65


def test_greedy_falls_back_to_random_when_scores_static():
    class NoScore(PickHigh):
        def scores(self, s):
            return [0.0] * self.n_players

    g = NoScore(2)
    rng = Random(1)
    s = g.setup(rng)
    assert GreedyAgent().act(g, s, g.legal_actions(s), rng) in [0, 1, 2]
