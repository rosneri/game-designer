The game package games/{slug}/ fails a check. Fix it with minimal, targeted changes.

{contract}

## Failure ({stage})
```
{error}
```

## Current files
{files}

{extra}
Time budget: you have about 8 minutes. If you use tools, check with the FAST commands only:
`uv run runner validate games/{slug}` (seconds) and `uv run runner sim games/{slug} --players N --games 60 --agents greedy,random`.
Run `uv run runner gauntlet games/{slug}` at most ONCE, right before answering. Do not iterate more than 3 times.
Return EVERY file you changed, complete, in path-tagged fenced blocks (```python path=games/{slug}/rules.py etc).
Do not return files you did not change. Keep the rules faithful to the docstring unless the docstring itself is wrong.
