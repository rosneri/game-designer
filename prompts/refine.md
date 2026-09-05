You are reviewing one batch of a self-improving card-game generator, and updating its learned-rules ledger.

The generator runs this pipeline per idea: idea (Fable) -> code (Opus) -> validate -> auto tests (Sonnet) ->
deterministic gauntlet (8 stages) -> LLM judge (Sonnet, scores 5 dimensions out of 10 each). The prompt
templates themselves are immutable. What you can change is the **ledger**: short rules that get injected into
later idea/code/fix prompts. Good entries are specific, checkable and derived from evidence in this run.

## Run {run} results
```json
{digest}
```

## Current ledger entries
```
{entries}
```

## Extra instructions
{instructions}

Propose at most {limit} edits. Rules:
- `create` a new entry only when the run gives real evidence for it; prefer `update` when an entry already
  covers the topic, and `delete` entries this run contradicts or that no longer earn their place.
- One idea per entry, imperative, under 200 characters, no preamble. Say the threshold or number when there is
  one ("mean legal actions must exceed 3 at every player count"), not a vague direction ("add more depth").
- `id` is stable kebab-case (reuse the existing id when updating). `kind` is one of note, memory, constraint,
  skill. `targets` picks the prompts it is injected into: idea, code, fix.
- Do not restate the pipeline, the contract, or anything already in the base prompts. Do not propose code
  changes here; that is a separate step.

Answer with a single ```json block only:
```json
{{"edits": [{{"op": "create", "id": "kebab-id", "kind": "constraint", "targets": ["idea"], "text": "the rule", "reason": "evidence from this run"}}]}}
```
