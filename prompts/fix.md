The game package games/{slug}/ fails a check. Fix it with minimal, targeted changes.

{contract}

## Harness notes (learned implementation rules)
{harness}

## Failure ({stage})
```
{error}
```

## Current files
{files}

{extra}
You work in an isolated workspace; the game lives at {game_dir} (games/{slug}/ relative to your cwd). Do not touch
anything outside it. Time budget: about 8 minutes. If you use tools, check with the FAST commands only:
`{validate_cmd}` (seconds) and `{sim_cmd}`.
Run `{gauntlet_cmd}` at most ONCE, right before answering. Do not iterate more than 3 times.
Return EVERY file you changed, complete, in path-tagged fenced blocks (```python path=games/{slug}/rules.py etc).
Do not return files you did not change. Keep the rules faithful to the docstring unless the docstring itself is wrong.
