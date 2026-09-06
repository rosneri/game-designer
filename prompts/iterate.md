You are redesigning an existing card game to make it better. This is a design pass, not a bug fix: the game
already works, passes its tests and clears the gauntlet. Your job is to raise the ceiling on how good it is.

{contract}

## Harness notes (learned design rules)
{harness}

## The game as it stands
{files}

## Deterministic metrics
```json
{metrics}
```

`s4_skill.skill_dominance` is how far a one-ply greedy bot beats random on a 0-1 scale; near 1 means the
obvious move is always right. `s5_decisions` gives mean legal actions per turn and the share of turns with no
choice. `s8_tension` gives lead changes per game, `decided_at` (how far into the game the winner takes their
final lead; 0.2 is a runaway leader) and comeback rate.

## Transcript of real play
```
{trace}
```

## What the reviewer said
Scores out of 10 — fun {fun}, clarity {clarity}, originality {originality}, depth {depth},
component_fit {component_fit} — total {total}/50, verdict "{verdict}".

{summary}

Notes:
{notes}

## Your task

Make ONE substantial design change that attacks the weakest dimension above, then follow it through the rules
so the game stays coherent. Read the transcript before you decide: it shows what actually happens at the table,
which is usually not what the rulesheet implies.

Rules for the change:
- Keep the game's identity. Same name, same slug, same core idea. A different game is a failure, not an
  improvement — the point is to make *this* game worth playing.
- Change the design, not the presentation. Rewording the rulesheet, renaming actions, or adding flavour text
  scores nothing. Change what players decide, what they risk, or how points arrive.
- Prefer a change that adds tension late: hidden or delayed scoring, a lever for the trailing player, a cost
  that makes the obviously good move wrong sometimes. Runaway leaders and forced turns are what sink these
  games.
- Keep it implementable and deterministic under the same contract, and keep the same components budget.
- Update `test_rules.py` for anything you change. It must still pass, and so must every gauntlet stage.

Explain the change and your reasoning in three or four sentences first. Then return EVERY file you changed,
complete, in path-tagged fenced blocks (```python path=games/{slug}/rules.py and so on). Do not return files
you did not change. The game directory is {game_dir}; do not touch anything outside it.
