# Game Designer Harness — Plan (v2, after user decisions)

## Decisions
- Player count 2–4. Dice: 0–2 × d6. Length target 10–30 min. Latest stable Python (3.14) via **proto**; tasks via **moonrepo**; packages via **uv workspace**.
- Some games can have an **AI GM** (narrator/adjudicator). At runtime the GM uses `ANTHROPIC_API_KEY` directly. For deterministic checks the GM is replaced by a `ScriptedGM`.
- The **generator harness** never calls the Anthropic API itself. It shells out to `prime-agent -p --no-session` so each call has **fresh context**:
  - `anthropic/claude-fable-5-1` → ideas and design plan
  - `anthropic/claude-opus-5` → rules code and fixes
  - `anthropic/claude-sonnet-5` → tests and LLM judge
- Loop: generate → deterministic gauntlet → LLM judge → learn (write lessons into prompts) → repeat.

## Monorepo layout
```
.prototools  .moon/{workspace,toolchain}.yml  pyproject.toml (uv workspace)
libs/
  cards/      Card, Deck (52 + 0–2 jokers), seeded shuffle
  dice/       d6 pool (0–2), seeded roll
  gamecore/   Game protocol, State, Action, Observation, play_game()
  agents/     RandomAgent, GreedyAgent, MCTSAgent
  gm/         GM protocol; ScriptedGM (deterministic); LLMGM (anthropic SDK)
  gauntlet/   stages s0..s7 + metrics + config
  report/     rulesheet + leaderboard
apps/
  generator/  the harness: idea → code → tests → gauntlet → judge → lessons (uses prime-agent CLI)
  runner/     the single game runner: `runner sim|play|gauntlet <game-dir>` for any game package
games/        generated game packages: <slug>/{spec.json, rules.py, test_rules.py, RULESHEET.md}
prompts/      prompt templates + LESSONS.md (updated after each run)
runs/         run logs: <timestamp>/<slug>/{idea.md, stages.json, judge.json}
```

## Game package contract
`rules.py` exposes `GAME: type[Game]` implementing `libs/gamecore` `Game` protocol. `spec.json` follows `GameSpec` (pydantic). Games needing a GM receive one through `setup(..., gm=...)`.

## Gauntlet (deterministic, runner app)
s0 schema · s1 import+smoke · s2 playable (random games terminate) · s3 balance (seat win rates) · s4 skill (greedy/MCTS > random, luck remains) · s5 decision density · s6 length band · s7 novelty fingerprint. Then **judge** (sonnet, fresh context, rubric → JSON scores).

## Generator pipeline (per idea, fresh context per step)
1. fable: idea brief + design plan (given LESSONS.md and a list of existing game names to avoid).
2. opus: write `rules.py` + `spec.json` per contract.
3. sonnet: write `test_rules.py`; run pytest.
4. runner gauntlet; on failure → opus fix (max 2 rounds) with failing stage output.
5. sonnet judge → `judge.json`.
6. Append lesson lines to `prompts/LESSONS.md` from failures.

## Steps
1. Skeleton + libs/cards, dice, gamecore, gm (me)
2. Parallel: libs/agents+gauntlet+report · 3 reference games · apps/runner · apps/generator
3. Run generator 3+ times, inspect failures, tune prompts/thresholds, repeat.
