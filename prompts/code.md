Implement the following card game as a Python game package that satisfies the Game protocol below.

{contract}

## Harness notes (learned implementation rules)
{harness}

## Game protocol (libs/gamecore/src/gd_gamecore/game.py, verbatim)
```python
{game_py}
```

## GameSpec (libs/gamecore/src/gd_gamecore/spec.py, verbatim)
```python
{spec_py}
```

{example}

## The game to implement (idea brief)
{idea}

Write games/{slug}/spec.json and games/{slug}/rules.py (relative to your working directory, an isolated workspace
whose only real package is this game; the absolute game dir is {game_dir}). Keep the code compact, well-structured
and faithful to the rules. If a rule is ambiguous, choose the simplest interpretation and document it in the docstring.
You may check your work with `{validate_cmd}` (seconds). Do not touch anything outside games/{slug}/.
Your FINAL answer MUST contain both complete files in path-tagged fenced blocks (the harness writes them from your answer).
