# game-designer

An AI harness that designs tabletop games, then makes them prove they're any good.

Each game is a small Python package: a `spec.json`, a `rules.py` that implements a shared `Game` protocol, tests, and a rulesheet. The harness writes the game with fresh-context agent calls, runs it through a **deterministic gauntlet** of simulated play, scores it with an **LLM judge**, and writes what went wrong back into the prompts so the next game starts smarter.

Constraints for every game: 2–4 players, a standard deck (plus up to two jokers) and 0–2 six-sided dice, 10–30 minutes. Some games include an AI game master; in deterministic checks it is swapped for a scripted one.

## The loop

```
idea + design plan ──▶ rules.py + spec.json ──▶ test_rules.py + pytest
        ▲                                                │
        │                                                ▼
  prompts/LESSONS.md ◀── judge (rubric → JSON) ◀── gauntlet s0–s7
                                                  (fix up to 2 rounds on failure)
```

Every step runs with fresh context, so no step can talk itself into a design it already committed to.

## The gauntlet

Deterministic stages, run by simulating many games with random, greedy, and MCTS agents:

| Stage | Checks |
| ----- | ------ |
| s0 | `spec.json` matches the schema |
| s1 | the package imports and a smoke game runs |
| s2 | random play always terminates |
| s3 | balance: seat win rates stay close |
| s4 | skill matters: greedy and MCTS beat random, but luck still exists |
| s5 | decision density: players face real choices |
| s6 | length lands in the target band |
| s7 | novelty: the game's fingerprint differs from existing games |

Only games that pass go to the judge. The judge reads play transcripts and tension metrics and scores out of 50. An iterate step can redesign a finished game, and a redesign is kept only if it beats the original by a margin, not a single point.

## Layout

```
libs/
  cards/      Card, Deck, seeded shuffle
  dice/       d6 pool, seeded roll
  gamecore/   Game protocol, State, Action, Observation, play_game()
  agents/     RandomAgent, GreedyAgent, MCTSAgent
  gm/         GM protocol: ScriptedGM (deterministic), LLMGM
  gauntlet/   stages s0–s7, metrics, config
  report/     rulesheet + leaderboard
apps/
  generator/  idea → code → tests → gauntlet → judge → lessons
  runner/     `runner gauntlet|sim|play|trace|validate <game-dir>` for any game package
  sourcing/   pulls BoardGameGeek categories, mechanics, and families into data/
games/        29 generated games: <slug>/{spec.json, rules.py, test_rules.py, gauntlet.json}
prompts/      prompt templates and LESSONS.md
```

## Running it

Python 3.14 via [proto](https://moonrepo.dev/proto), tasks via [moon](https://moonrepo.dev), packages via a [uv](https://docs.astral.sh/uv/) workspace.

```bash
uv sync
uv run pytest -q libs apps
uv run runner gauntlet games/kiln    # run the gauntlet on one game
uv run runner trace games/kiln       # print one readable game transcript
uv run runner play games/kiln        # play it as seat 0 against greedy agents
```

The generator shells out to an agent CLI for each step. Games with an AI game master need `ANTHROPIC_API_KEY` at play time.

See [PLAN.md](PLAN.md) for the full design.
