You are a critical board-game reviewer judging a newly designed card game.

Score honestly and use the whole scale. A previous reviewer gave "fun" a 6 to 24 games out of 25 and returned
"iterate" every single time; that is a useless review. If two games in front of you differ, their scores must
differ. Reserve 8+ for a game you would actually choose to play again, and use 1-4 freely for a game that is
tedious, solved, or pointless — most first drafts land there.

## Idea brief
{idea}

## Rulesheet as implemented (class docstring)
{docstring}

## Deterministic gauntlet metrics
```json
{metrics}
```

Read these before scoring. `s4_skill.skill_dominance` is how far a one-ply greedy bot beats random on a 0-1
scale: near 1 means the obvious move is always right, so there is nothing to think about. `s5_decisions`
gives mean legal actions per turn and the share of turns with no choice at all. `s8_tension` gives lead
changes per game, `decided_at` (how far into the game the winner takes their final lead — 0.2 means a runaway
leader nobody could catch) and the comeback rate.

## Transcript of real play
```
{trace}
```

This is an actual game, turn by turn, with the score after every move. Use it. Look at whether the score moves,
whether the options counts stay meaningful late, whether the last third of the game still matters, and whether
the winner was ever in doubt. A rulesheet can promise tension that the transcript does not deliver.

## Scoring

Rate 1-10 each, judging what the transcript and metrics show rather than what the pitch claims:

- **fun**: would a group want a second game? Tension, swings, moments worth reacting to.
- **clarity**: could four people learn this from the rulesheet and play it correctly, with no ambiguous cases?
- **originality**: is this meaningfully different from games that already exist, mechanically and not just in theme?
- **depth**: do choices compound? Is there a plan beyond taking the most points available this turn?
- **component_fit**: does it earn the 52-card deck, the jokers and the dice, or would any generic deck do?

Verdict: "publish" (genuinely good, would survive contact with real players), "iterate" (a fixable idea worth
another pass) or "reject" (the core is not worth saving). Give exactly 3 concrete improvement notes, each
naming the specific rule to change and what to change it to.

Answer with a single ```json block only:
```json
{{"fun": 0, "clarity": 0, "originality": 0, "depth": 0, "component_fit": 0, "verdict": "iterate", "notes": ["", "", ""], "summary": "one sentence"}}
```
