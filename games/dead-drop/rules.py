"""Dead Drop — face-down exchanges around three shared drops, then a public ledger.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck, no jokers, no dice.

Ranks: A=1, 2-10 face value, J=11, Q=12, K=13. **The ace is low only**: it is adjacent to the 2
and never adjacent to the king. Cards are written rank + suit letter, e.g. ``9H``, ``AS``,
``10D``; suits are S(pades), H(earts), D(iamonds), C(lubs).

Setup
-----
Shuffle the deck. Deal 3 cards face down to each player as a hand. Place 3 cards face down in a
row in the centre as **drops 0, 1 and 2**. Nobody looks at the drops. The rest of the deck is
the face-down draw pile. Each player starts with an empty **ledger** (a face-up row of cards in
front of them) and a score of 0. Seat 0 takes the first turn; play is clockwise (0, 1, 2, 3).

A turn
------
A turn has two steps, in this order: an optional **Exchange**, then a mandatory **Placement**.

**Step 1: Exchange (optional).** The active player chooses exactly one of:

* **Pass** — do nothing.
* **Drop swap** — choose a card from your hand and a drop 0-2. Take that drop's card into your
  hand and look at it, then put your chosen card face down into the same drop. Everyone sees
  *which* drop you used; nobody sees either card.
* **Player swap** — choose a card from your hand and an opponent. Give that card face down to
  the opponent. The opponent must then choose one card from their own hand and hand it back
  face down, **before looking at the card they received**. The opponent may not decline. Both
  players then add the received card to their hand. Everyone sees who swapped with whom; nobody
  sees the cards.

**Step 2: Placement (mandatory).** The active player takes one card from hand and places it face
up in their own ledger:

* If the ledger is empty, that card becomes the ledger and scores 0.
* Otherwise the card goes on the **left end** or the **right end** of the row. It then has
  exactly one neighbour: the card that was previously at that end. Score the highest matching
  line of this table, added to your score at once:

  | condition (new card vs. its one neighbour)          | points |
  |-----------------------------------------------------|--------|
  | same rank                                            |   5    |
  | same suit and ranks differ by exactly 1               |   4    |
  | same suit, ranks differ by 2 or more                  |   2    |
  | different suit and ranks differ by exactly 1          |   1    |
  | anything else                                        |   0    |

After placing, the active player draws 1 card from the draw pile if it is not empty. If the
draw pile is empty, no card is drawn.

End of the game
---------------
Each ledger is closed after **8 cards**. The game ends the moment the last seat places its 8th
card, so every player takes exactly 8 turns and places exactly 8 cards. Hands never run empty —
a player always still holds at least 2 cards when the game ends.

Draw pile size is 49 − 3 × players: 43 cards with 2 players, 40 with 3, 37 with 4, so the pile
never runs out before the 8th round ends.

The cipher payout
-----------------
Right after the last placement, turn over the top card of the draw pile: this is the **cipher**,
and nobody knows it in advance. Every player then scores a payout from their own closed ledger:

* each ledger card of the **cipher's suit** pays points equal to its own rank (A=1 ... K=13);
* each ledger card of the **cipher's rank** pays a flat 10 points (a card can pay both).

The payout is added to the points collected during play. A ledger stacked with one suit is a
gamble: it pays a fortune when the cipher matches and nothing when it does not.

Scoring and winner
------------------
Most points, play plus payout, wins. Tie-break, in order:
  1. higher sum of the ranks of all cards in your ledger (A=1 ... K=13);
  2. the higher seat index (later in turn order).
This is always decisive, so a finished game is never a draw. This implementation folds the two
tie-breaks into ``scores`` as tiny fractions (< 1/2), so the ranking is exact; the whole-number
part of a score is always the real point total.

Clarifications (chosen readings of the rules)
---------------------------------------------
* A card taken from a drop may be placed on the same turn, before anyone else can see it. That
  is allowed and is the point of the game.
* A drop always holds exactly one card; a drop swap is the only way a card leaves a drop, and
  drop contents are never revealed publicly (not even at the end).
* The responder in a player swap chooses their return card knowing only who initiated. Their
  hand at that moment does **not** yet contain the incoming card, so they cannot hand it back.
* The exchange step may be used every turn, without limit, but each turn contains exactly one
  placement, so every player closes their ledger on the same round.
* The cipher is drawn only after the final placement, so no play decision can be made with the
  cipher known; spreading suits is the safe line, hoarding one suit is the greedy line.
* Both ``L`` and ``R`` are offered when the ledger holds a single card: the neighbour and the
  score are the same, but the resulting row order differs.
* A public event log (who used which drop, who swapped with whom, what each player placed) is
  visible to everybody — that is the memory material of the game.

Strategy note: the drops are a shared memory puzzle. Stash a card you want to come back to, and
count on rivals forgetting; shove your dead cards at the player whose ledger ends are hottest.
With only 8 slots per ledger, a big cipher payout can beat a tidy but colourless ledger.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_gamecore import GMLike

SUITS = "SHDC"
RANK_NAMES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
HAND = 3
DROPS = 3
LEDGER = 8  # cards per ledger; the game ends when every ledger is full
ENDS = ("L", "R")


def rank_of(cid: str) -> int:
    """Rank value of a card id, ace low (``AS`` -> 1, ``10D`` -> 10, ``KH`` -> 13)."""
    return RANK_NAMES.index(cid[:-1]) + 1


def suit_of(cid: str) -> str:
    return cid[-1]


def full_deck() -> list[str]:
    return [r + s for s in SUITS for r in RANK_NAMES]


def pair_points(new: str, nb: str) -> int:
    """Points for placing ``new`` next to neighbour ``nb`` (highest matching line wins)."""
    dr = abs(rank_of(new) - rank_of(nb))
    same_suit = suit_of(new) == suit_of(nb)
    if dr == 0:
        return 5
    if same_suit:
        return 4 if dr == 1 else 2
    return 1 if dr == 1 else 0


@dataclass
class DeadDropState:
    """Mutable state; ``step`` always works on a deep copy of its input."""

    hands: list[list[str]]
    drops: list[str]
    deck: list[str]  # top of the pile is the last element
    ledgers: list[list[str]]
    points: list[int]
    current: int
    phase: str = "exchange"  # "exchange" | "respond" | "place" | "over"
    pending: tuple[int, int, str] | None = None  # (initiator, responder, card given by initiator)
    cipher: str | None = None  # revealed only after the last placement
    log: list[tuple] = field(default_factory=list)  # public events, everybody sees these


class DeadDrop:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> DeadDropState:
        deck = full_deck()
        rng.shuffle(deck)
        hands = [[deck.pop() for _ in range(HAND)] for _ in range(self.n_players)]
        drops = [deck.pop() for _ in range(DROPS)]
        return DeadDropState(
            hands=hands,
            drops=drops,
            deck=deck,
            ledgers=[[] for _ in range(self.n_players)],
            points=[0] * self.n_players,
            current=0,
        )

    def current_player(self, s: DeadDropState) -> int:
        if s.phase == "respond" and s.pending is not None:
            return s.pending[1]
        return s.current

    def legal_actions(self, s: DeadDropState) -> list[tuple]:
        if s.phase == "over":
            return []
        p = self.current_player(s)
        hand = sorted(s.hands[p], key=lambda c: (SUITS.index(suit_of(c)), rank_of(c)))
        if s.phase == "exchange":
            acts: list[tuple] = [("pass",)]
            acts += [("drop", c, d) for c in hand for d in range(DROPS)]
            acts += [("offer", c, q) for c in hand for q in range(self.n_players) if q != p]
            return acts
        if s.phase == "respond":
            return [("give", c) for c in hand]
        ends = ENDS if s.ledgers[p] else ("L",)
        return [("place", c, e) for c in hand for e in ends]

    def step(self, state: DeadDropState, a: tuple, rng: Random) -> DeadDropState:
        s = copy.deepcopy(state)
        if s.phase == "over":
            raise ValueError("game is over")
        p = self.current_player(s)
        kind = a[0]
        if kind == "pass" and s.phase == "exchange":
            s.log.append(("pass", p))
            s.phase = "place"
        elif kind == "drop" and s.phase == "exchange":
            _, cid, d = a
            self._take(s, p, cid)
            if not 0 <= d < DROPS:
                raise ValueError(f"bad drop {d}")
            s.hands[p].append(s.drops[d])
            s.drops[d] = cid
            s.log.append(("drop", p, d))
            s.phase = "place"
        elif kind == "offer" and s.phase == "exchange":
            _, cid, q = a
            if not 0 <= q < self.n_players or q == p:
                raise ValueError(f"bad target seat {q}")
            self._take(s, p, cid)
            s.pending = (p, q, cid)
            s.log.append(("offer", p, q))
            s.phase = "respond"
        elif kind == "give" and s.phase == "respond":
            init, resp, given = s.pending  # type: ignore[misc]
            back = a[1]
            self._take(s, resp, back)
            s.hands[init].append(back)
            s.hands[resp].append(given)
            s.pending = None
            s.phase = "place"
        elif kind == "place" and s.phase == "place":
            self._place(s, p, a[1], a[2])
        else:
            raise ValueError(f"illegal action {a!r} in phase {s.phase}")
        return s

    # -- helpers -------------------------------------------------------------------------
    @staticmethod
    def _take(s: DeadDropState, p: int, cid: str) -> None:
        if cid not in s.hands[p]:
            raise ValueError(f"{cid} not in hand of seat {p}")
        s.hands[p].remove(cid)

    def _place(self, s: DeadDropState, p: int, cid: str, end: str) -> None:
        if end not in ENDS:
            raise ValueError(f"bad end {end!r}")
        self._take(s, p, cid)
        led = s.ledgers[p]
        gain = 0
        if not led:
            led.append(cid)
        elif end == "L":
            gain = pair_points(cid, led[0])
            led.insert(0, cid)
        else:
            gain = pair_points(cid, led[-1])
            led.append(cid)
        s.points[p] += gain
        s.log.append(("place", p, cid, end, gain))
        if s.deck:
            s.hands[p].append(s.deck.pop())
        if all(len(l) >= LEDGER for l in s.ledgers):
            self._payout(s)
            s.phase = "over"
            return
        s.current = (p + 1) % self.n_players
        s.phase = "exchange"

    def _payout(self, s: DeadDropState) -> None:
        """Reveal the cipher and pay every closed ledger (see the rulesheet)."""
        if s.deck:
            s.cipher = s.deck.pop()
            csuit, crank = suit_of(s.cipher), rank_of(s.cipher)
            for p in range(self.n_players):
                bonus = 0
                for c in s.ledgers[p]:
                    if suit_of(c) == csuit:
                        bonus += rank_of(c)
                    if rank_of(c) == crank:
                        bonus += 10
                s.points[p] += bonus
                s.log.append(("payout", p, bonus))
        s.log.append(("cipher", s.cipher))

    # -- results -------------------------------------------------------------------------
    def is_terminal(self, s: DeadDropState) -> bool:
        return s.phase == "over"

    def scores(self, s: DeadDropState) -> list[float]:
        """Points, plus the two tie-breaks folded in as fractions below 1/2."""
        return [
            float(s.points[p]) + 1e-4 * sum(rank_of(c) for c in s.ledgers[p]) + 1e-7 * p
            for p in range(self.n_players)
        ]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: DeadDropState, p: int) -> tuple:
        """Seat ``p`` sees its own hand, every ledger and score, and the public event log."""
        pend = None
        if s.pending is not None:
            pend = (s.pending[0], s.pending[1])  # the card in flight stays hidden
        return (
            ("you", p),
            ("phase", s.phase),
            ("to_act", self.current_player(s) if s.phase != "over" else -1),
            ("hand", tuple(sorted(s.hands[p]))),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("ledgers", tuple(tuple(l) for l in s.ledgers)),
            ("points", tuple(s.points)),
            ("deck", len(s.deck)),
            ("drops", DROPS),  # contents are secret
            ("pending", pend),
            ("cipher", s.cipher),
            ("log", tuple(s.log)),
        )

    def describe(self, s: DeadDropState) -> str:
        led = "; ".join(f"s{p}:{'-'.join(l) or 'empty'}" for p, l in enumerate(s.ledgers))
        who = "-" if s.phase == "over" else f"seat {self.current_player(s)}"
        return (
            f"phase={s.phase} to_act={who} points={s.points} deck={len(s.deck)} "
            f"cipher={s.cipher or '?'} "
            f"hands={[len(h) for h in s.hands]} | ledgers {led}"
        )


GAME = DeadDrop
