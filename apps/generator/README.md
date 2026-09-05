# generator

The flywheel: generate a card game, test it deterministically, judge it, learn from what happened, then improve
the harness that did all of that — and go again.

```
generator flywheel --cycles 5 --n 8 --parallel 3
    │
    ├── run      idea → code → validate → tests → gauntlet → judge → promote   (per idea, isolated)
    ├── learn    run lessons  → prompts/LESSONS.md
    ├── refine   run evidence → prompts/harness_state.json   (learned rules, reversible)
    └── improve  run evidence → the harness's own code       (gated by tests + lint, auto-reverted)
```

## Isolation model

| boundary | what it protects |
|---|---|
| `runs/<run>/snapshot/` | prompts, lessons and the catalog are frozen when the run starts; edits made mid-run (by you, or by the improve step of another run) cannot change what this run is doing |
| `runs/<run>/ideaNN/workspace/` | each idea builds its own `games/<slug>/` there, with spec-only shadows of the catalog so the novelty stage still works; the coding agent gets this as its working directory and never sees the real repo |
| `promote` | a survivor is copied into `games/<slug>/` only at the very end, through a temp dir and one atomic rename |
| `steps/<name>.json` | each step records status, model, timing, retries and artifacts, so `resume` can skip what already succeeded |
| `manifest.json` | run id, seed, git sha, model routes, prompt hashes, catalog and ledger size — what produced these games |
| `PYTHONPYCACHEPREFIX` | per-idea bytecode cache, so parallel workers never share `__pycache__` |

Nothing is shared between ideas except the registry (slug allocation and dedupe, ordered by idea index so the
outcome depends on the seed rather than thread timing) and the lesson board.

## Learning, game by game

In the default `rolling` mode each worker takes one idea from start to finish and publishes its lessons the
moment it lands, so an idea that starts later sees what earlier games taught and which briefs already exist.
`--mode phased` restores the old behaviour (all ideas first, then all builds). `--no-live-lessons` keeps the
run reproducible from its snapshot alone.

Three feedback channels, in increasing order of durability:

1. **Lesson board** — within one run, in memory, rendered into later idea prompts as `(this run) …`.
2. **`prompts/LESSONS.md`** — `generator learn <run>` folds a finished run's `lessons.jsonl` into bullets.
   Infrastructure failures (billing, rate limits, timeouts) are classified by `is_infra_error` and never become
   design lessons.
3. **`prompts/harness_state.json`** — the continual-harness ledger, modelled on prime-agent's. Prompt templates
   are the immutable base; the ledger holds short learned rules that are injected into the idea/code/fix
   prompts. `generator refine <run>` proposes a bounded batch of create/update/delete edits, applies them with
   before/after snapshots, and prints an event id. `generator rollback <event>` undoes exactly that batch.

## Self-improvement

`generator improve <run>` hands the coding model the run's evidence, the ledger, and the history of what has
already been tried, with write access to `prompts/`, `libs/`, `apps/` and the threshold files — never to
`games/` or `runs/`. The allow-listed tree is snapshotted first; afterwards the gates run:

```
uv run pytest -q libs apps
uv run ruff check libs apps
```

If any gate fails, every touched file is restored byte for byte and the attempt is recorded as reverted, so the
next cycle knows not to try it again. Only a change that keeps the suite green survives.

**Run it as the only writer.** The revert restores every file whose bytes changed during the call, so anything
another agent or editor saves into `prompts/`, `libs/` or `apps/` while the step is running would be rolled
back with it. Batches are safe to run alongside other work (they only write `runs/` and, at the very end, one
game directory); `improve` is not.

## Commands

```bash
generator run --n 10 --seed 3 --parallel 3      # a batch (parallel defaults to 3)
generator resume runs/20260905-1200             # finish an interrupted run; re-runs infra failures only
generator flywheel --cycles 5 --n 8             # run → learn → refine → improve, repeatedly
generator refine runs/<run>                     # ledger edits from one run's evidence
generator improve runs/<run> [--dry-run]        # patch the harness itself, behind gates
generator learn runs/<run>                      # fold lessons into prompts/LESSONS.md
generator harness                               # print the ledger
generator rollback <event-id>                   # undo one refinement
generator report runs/<run>                     # rewrite REPORT.md
generator dry-run --n 2                         # print prompts, call nothing
```

## Configuration

Defaults live in `GeneratorConfig`; override them in `generator.toml` at the repo root, then per-invocation
flags on top. Environment variables `GD_PRIME_AGENT_BIN`, `GD_CLAUDE_BIN`, `GD_RUNNER_CMD` and `GD_PYTEST_CMD`
swap the binaries (the test suite uses this to run the whole pipeline against stubs).

```toml
[generator]
parallel = 3
mode = "rolling"          # or "phased"
live_lessons = true
dedupe_similarity = 0.75  # cull a brief whose mechanic tags overlap this much with the catalog or a peer
improve_paths = ["prompts", "libs", "apps", "gauntlet.toml", "generator.toml"]

[generator.steps.idea]
backend = "claude"        # Fable 5.1 on the subscription; prime-agent's OAuth path is version-gated for it
model = "anthropic/claude-fable-5-1"
timeout = 600
```

Model routing per step is data, not code: `idea` and `refine` run on Fable, `code`/`fix`/`improve` on Opus with
tools, `tests`/`judge` on Sonnet. The `claude` backend strips `ANTHROPIC_API_KEY` from the subprocess so the
harness bills the subscription, leaving the key for the runtime LLM game master.
