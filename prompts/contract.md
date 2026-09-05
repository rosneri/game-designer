Game package contract (games/<slug>/):
- spec.json: a GameSpec JSON object. Fields: slug (^[a-z][a-z0-9-]{2,40}$), name, tagline, players_min (2-4),
  players_max (2-4), components {jokers 0-2, dice 0-2, uses_full_deck bool, extra []}, mechanics [tags],
  core_loop, win_condition, est_minutes [lo, hi], gm {enabled false, role "", decisions []},
  hidden_information bool, turn_order "clockwise"|"simultaneous"|"variable".
- rules.py: defines `GAME: type[Game]`. `GAME.__init__(self, n_players: int, gm: GMLike | None = None)` sets
  `self.n_players`. The class docstring IS the rulesheet (full rules in prose, players read only this).
- Pure and deterministic: ALL randomness via the `rng: random.Random` passed to setup/step. Never use the
  `random` module directly, never `time`, never I/O, no network.
- `step` must NOT mutate the input state: start with `s = copy.deepcopy(state)` (or build new immutable state).
- Actions are hashable with a readable str(): tuples of str/int like ("play", "7H") or ("pass",).
- `legal_actions` is non-empty for every non-terminal state. `scores` returns a list of floats of length n_players.
- `observe(s, p)` hides other players' private information. `describe(s)` is a short human-readable text.
- Only stdlib + gd_gamecore (+ optional gd_cards, gd_dice) imports. The game MUST terminate in < 2000 steps.
- If a GM is needed, use `self.gm.decide(prompt, options, context)` and fall back to `options[0]` when gm is None.
Return the complete files inside fenced blocks tagged with their path, exactly like:
```python path=games/<slug>/rules.py
...
```
```json path=games/<slug>/spec.json
...
```
