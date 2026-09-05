Write pytest tests for the game package games/{slug}/ as games/{slug}/test_rules.py.

Available helpers:
```python
from gd_gamecore import play_game, load_game_module   # play_game(game, agents, seed, max_turns=2000, record=False) -> PlayResult
from gd_agents import RandomAgent                       # RandomAgent().act(game, state, legal, rng)
```
PlayResult fields: `scores: list[float]`, `turns: int`, `winners: list[int]`, `error: str | None`,
`final_state` (the last state reached; use THIS for end-of-game checks), `history: list[TurnRecord(player, n_legal, action)]`
which is EMPTY unless you pass `record=True` and never contains states. Do not index `history` for a state.
Load the game with `GAME = load_game_module(Path(__file__).parent).GAME` and instantiate `GAME(n)` for each
supported player count ({players}).

Required invariants (each its own test, parametrised over player counts and a few seeds):
1. terminates: play_game(...).error is None and turns > 0.
2. scores: `len(game.scores(result.final_state)) == n_players` and all entries are numbers.
3. no mutation: `before = copy.deepcopy(s); game.step(s, a, rng); assert s == before` on several states.
4. legal actions: non-empty and all hashable for every non-terminal state along a random playout.
5. observe: `game.observe(s, p)` works for every player and does not raise.
Add 1-2 game-specific tests derived from the rulesheet (docstring) below if they are cheap and robust.
Keep tests deterministic (fixed seeds) and fast (< 5 s total).

## Rulesheet
{docstring}

## rules.py
```python
{rules}
```

Return the complete test file in one fenced block: ```python path=games/{slug}/test_rules.py
