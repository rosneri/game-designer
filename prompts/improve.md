You are improving a self-improving card-game generator by editing its own code. Repo root: {root}

The generator runs, per idea: idea (Fable) -> code (Opus) -> validate -> auto tests (Sonnet) -> deterministic
gauntlet (8 stages, thresholds in libs/gauntlet .. GauntletConfig and gauntlet.toml) -> LLM judge (Sonnet).
`apps/generator` orchestrates it; `apps/runner` runs a single game; `libs/*` hold the reusable pieces.
Run artefacts live under runs/<run>/ and generated games under games/<slug>/.

## Evidence from run {run}
```json
{digest}
```

## Ledger (what the harness has already learned)
```
{harness}
```

## Recent refinement events
```json
{history}
```

## Extra instructions
{instructions}

## Your task
Make ONE focused improvement to the harness that this evidence supports: a gauntlet threshold that let a bad
game through, a prompt template that produced a recurring mistake, a judge that does not discriminate, a
missing metric, a wasteful step, a bug. Prefer the smallest change with the largest effect on the quality of
generated games. Explain your reasoning in two or three sentences before you edit.

Rules:
- Edit files directly with your tools. You may only touch:
{paths}
  Never touch games/, runs/, .git/, or any generated game package.
- Keep every public API used elsewhere working, and update the tests that cover what you change.
- These gates run right after you answer, and your change is reverted in full if any of them fails:
```
{gates}
```
  So run them yourself before you finish, and fix what you break.
- Do not repeat an improvement the ledger says was already applied or already reverted.
- If the evidence does not support any change you are confident in, change nothing and say so.

Finish with a short summary: what you changed, in which files, and what you expect it to do to the next batch.
