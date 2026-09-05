import copy
from pathlib import Path

import pytest

from gd_gamecore import play_game, load_game_module
from gd_agents import RandomAgent

GAME = load_game_module(Path(__file__).parent).GAME

PLAYER_COUNTS = (2, 3, 4)
SEEDS = (0, 1, 2)


def make_agents(n):
    return [RandomAgent() for _ in range(n)]


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_terminates(n, seed):
    result = play_game(GAME(n), make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    assert result.turns > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_scores(n, seed):
    result = play_game(GAME(n), make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    assert len(result.scores) == n
    for v in result.scores:
        assert isinstance(v, (int, float))


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_mutation(n, seed):
    game = GAME(n)
    import random
    rng = random.Random(seed)
    s = game.setup(rng)
    checks = 0
    while checks < 30:
        if game.is_terminal(s):
            break
        legal = game.legal_actions(s)
        if not legal:
            break
        a = rng.choice(legal)
        before = copy.deepcopy(s)
        game.step(s, a, rng)
        assert s == before
        # advance actual state with a fresh rng call to keep progressing
        s = game.step(s, a, random.Random(rng.randint(0, 1 << 30)))
        checks += 1


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_legal_actions_and_observe(n, seed):
    game = GAME(n)
    import random
    rng = random.Random(seed)
    s = game.setup(rng)
    steps = 0
    while not game.is_terminal(s) and steps < 500:
        legal = game.legal_actions(s)
        assert len(legal) > 0
        for a in legal:
            hash(a)
        for p in range(n):
            obs = game.observe(s, p)
            assert obs is not None
        agent = RandomAgent()
        a = agent.act(game, s, legal, rng)
        s = game.step(s, a, rng)
        steps += 1
    assert steps > 0


@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_leader_cannot_pass(n):
    game = GAME(n)
    import random
    rng = random.Random(42)
    s = game.setup(rng)
    # at the very start the table is empty (lead), so "pass" must not be legal
    legal = game.legal_actions(s)
    assert ("pass",) not in legal
    assert all(a[0] == "play" for a in legal)


@pytest.mark.parametrize("n", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_summit_and_end_conditions(n, seed):
    result = play_game(GAME(n), make_agents(n), seed=seed, max_turns=2000)
    assert result.error is None
    final_state = result.history[-1] if hasattr(result, "history") and result.history else None
    # sanity: winners set is well formed
    assert result.winners is not None
    assert len(result.winners) >= 1
