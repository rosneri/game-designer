Implement the following card game as a Python game package that satisfies the Game protocol below.

{contract}

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

Write games/{slug}/spec.json and games/{slug}/rules.py. Keep the code compact, well-structured and faithful to the
rules. If a rule is ambiguous, choose the simplest interpretation and document it in the docstring.
You may read repository files and run `uv run runner validate games/{slug}` to check your work, but your FINAL
answer MUST contain both complete files in path-tagged fenced blocks (the harness writes them from your answer).
