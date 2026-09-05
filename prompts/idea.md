You are a veteran card-game designer. Design ONE new, original game for a standard 52-card deck.

Hard constraints:
- 2 to 4 players (state the exact supported range).
- Components: the 52-card deck, 0-2 jokers, 0-2 six-sided dice. Nothing else (no boards, no pen and paper if avoidable).
- Length 10-30 minutes. Our simulator estimates time as turns x (6s + 6s x log2(options per turn)). So target
  roughly 40-150 total decision turns per game at every player count (e.g. 2 players must NOT finish in 15 turns).
  Every turn must offer a real decision (2+ meaningful options most turns).
- A greedy one-step-lookahead bot must beat random players clearly (skill matters), but must not win 100%
  at every player count (luck must exist). Prefer scoring that responds to each single action.
- No ties for first place in most games: include a deterministic tie-break.
- Rules must be fully implementable as a deterministic state machine with a clear end condition.
- Do NOT duplicate any existing game below.

Seed direction to explore (bend it, but keep it): {direction}

{taxonomy}

Existing games (avoid these names and near-identical mechanics):
{existing}

Lessons from earlier runs (respect them):
{lessons}

Harness notes (learned rules; treat as hard guidance):
{harness}

Answer in exactly this Markdown structure:

# <Name>
slug: <lowercase-kebab, 3-40 chars>
players: <min>-<max>
jokers: <0|1|2>
dice: <0|1|2>
mechanics: <comma separated tags, 2-5 of them, drawn from the Mechanics/Categories lists above (kebab-case, e.g. trick-taking, set-collection); coin a new tag only if nothing above fits>
hidden_information: <true|false>
turn_order: <clockwise|simultaneous|variable>

## Pitch
One paragraph.

## Rules
Complete rules in prose: setup, turn structure, all special cases, end of game, scoring, tie-breaks.
Be precise enough that a programmer can implement them without asking questions.

## Design plan
- State: fields needed (hands, piles, scores, current player, phase, ...)
- Actions: the full action space as hashable tuples/strings
- Turn flow: how phases advance, when the game ends
- Randomness: where the rng is used (shuffle, dice)
