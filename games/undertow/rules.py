"""Undertow — push your luck against a shared hazard.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers, no dice).

Card points: Ace 1, number cards their pip value, Jack 11, Queen 12, King 13. Suits never matter.

Setup
-----
Shuffle the deck face down and flip its top card face up beside it: that card is the **Undertow**,
a hazard shared by everybody. Next to the deck leave room for a face-up discard pile, the **Wreck**
(it starts empty). Each diver has two zones: a **Haul** (face-up row, starts empty) and a **Hold**
(face-down stack, starts empty). Seat 0 starts; play goes clockwise.

Score
-----
At any moment your score is the points of every card in your Hold plus the points of every card in
your Haul. Hold cards are safe forever. Haul cards can still wash away.

Bust ranks
----------
For you, a rank is a **bust rank** if it is the rank of the Undertow or the rank of any card that is
currently in your Haul. If there is no Undertow any more (see End of game) only your Haul ranks count.
Because of this rule your Haul never holds two cards of the same rank.

Turn
----
On your turn take exactly one action.

1. **Draw** — legal only while the deck has cards. Reveal the top card of the deck.
   * If its rank is one of your bust ranks you **bust**: that card and every card of your Haul go
     face up on the Wreck (the drawn card on top) and your Haul is empty.
   * Otherwise the card joins your Haul.
2. **Salvage** — legal only if the Wreck is not empty and the rank of its top card is not one of your
   bust ranks. Move that top Wreck card into your Haul.
3. **Bank** — legal only if your Haul holds at least one card. Move the whole Haul face down into
   your Hold. If you banked **three or more** cards at once you also take the Undertow card into your
   Hold and flip the top card of the deck as the new Undertow (if the deck is empty there is no
   Undertow for the rest of the game; if there was no Undertow to take, you just bank). Then resolve
   Caught.
4. **Pass** — legal only when none of the three actions above is legal. Nothing happens.

Caught
------
Every time a new Undertow is flipped, each *other* player must drop from their Haul any card whose
rank matches the new Undertow; those cards go on top of the Wreck, resolved in seat order starting
with the player left of the banker, one card at a time. The banker's Haul is empty at that moment,
so the banker is never Caught.

End of game
-----------
The moment the deck runs empty — by a draw or by an Undertow flip — the **final round** begins. Play
continues clockwise until the player seated immediately to the right of the start player has finished
a turn, so everybody has taken the same number of turns. During the final round Draw is illegal;
Salvage, Bank and Pass remain. Then the game ends.

Final scoring
-------------
Each diver scores Hold points plus Haul points; an unbanked Haul still counts, it simply never earned
an Undertow bonus. Highest score wins. Ties are broken in this order: most cards in the Hold; then the
highest single card value in the Hold; then the fewest cards left in the Haul; then the higher seat
number (later in turn order) wins, which compensates the later divers a little. This implementation
folds the tie-break into ``scores()`` as a fraction smaller than one point, so the reported score is
"points + tie-break dust".

Note on the deck: the deck order is not modelled; each reveal takes a uniformly random card from the
cards still face down, which is exactly the same as drawing off a shuffled pile. Everything else is
public — the Wreck, both Hauls and Hold totals, therefore the exact set of cards still hidden. Counting
what is left is the skill; guessing when the tide turns is the luck.

Worked example
--------------
The Undertow is 9S and your Haul is 4H KD, so your bust ranks are 9, 4 and K. The Wreck shows 4C on
top, so Salvage is illegal: you may Draw or Bank. You Draw 7C and add it. Next turn you Bank three
cards (24 points), take the 9S (9 points) into your Hold and flip a new Undertow, 7D. Your left-hand
neighbour holds 7S in their Haul and is Caught: the 7S goes to the Wreck.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random

from gd_cards import Card, standard_deck
from gd_gamecore import GMLike

BANK_BONUS = 3  # cards you must bank at once to claim the Undertow


@dataclass(frozen=True)
class UndertowState:
    deck: tuple[Card, ...]  # cards still face down (order irrelevant: draws pick at random)
    wreck: tuple[Card, ...]  # discard pile, top card last
    undertow: Card | None
    hauls: tuple[tuple[Card, ...], ...]
    holds: tuple[tuple[Card, ...], ...]
    current: int
    final_round: bool = False
    over: bool = False


class Undertow:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> UndertowState:
        deck = standard_deck()
        rng.shuffle(deck)
        undertow = deck.pop()
        empty: tuple[tuple[Card, ...], ...] = tuple(() for _ in range(self.n_players))
        return UndertowState(tuple(sorted(deck)), (), undertow, empty, empty, 0)

    def current_player(self, s: UndertowState) -> int:
        return s.current

    # -- rules helpers -------------------------------------------------------------------
    def _bust_ranks(self, s: UndertowState, p: int) -> set[int]:
        ranks = {c.rank for c in s.hauls[p]}
        if s.undertow is not None:
            ranks.add(s.undertow.rank)
        return ranks

    def legal_actions(self, s: UndertowState) -> list[tuple]:
        p = s.current
        bust = self._bust_ranks(s, p)
        out: list[tuple] = []
        if s.deck and not s.final_round:
            out.append(("draw",))
        if s.wreck and s.wreck[-1].rank not in bust:
            out.append(("salvage",))
        if s.hauls[p]:
            out.append(("bank",))
        return out or [("pass",)]

    def step(self, s: UndertowState, a: tuple, rng: Random) -> UndertowState:
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        p = s.current
        deck, wreck = list(s.deck), list(s.wreck)
        hauls = [list(h) for h in s.hauls]
        holds = [list(h) for h in s.holds]
        undertow = s.undertow

        if a == ("draw",):
            card = deck.pop(rng.randrange(len(deck)))
            if card.rank in self._bust_ranks(s, p):
                wreck.extend(sorted(hauls[p]))
                wreck.append(card)
                hauls[p] = []
            else:
                hauls[p].append(card)
        elif a == ("salvage",):
            hauls[p].append(wreck.pop())
        elif a == ("bank",):
            banked = len(hauls[p])
            holds[p].extend(hauls[p])
            hauls[p] = []
            if banked >= BANK_BONUS and undertow is not None:
                holds[p].append(undertow)
                undertow = deck.pop(rng.randrange(len(deck))) if deck else None
                if undertow is not None:  # Caught: neighbours drop the matching rank
                    for k in range(1, self.n_players):
                        q = (p + k) % self.n_players
                        keep = [c for c in hauls[q] if c.rank != undertow.rank]
                        wreck.extend(c for c in hauls[q] if c.rank == undertow.rank)
                        hauls[q] = keep
        # ("pass",): nothing happens

        final_round = s.final_round or not deck
        over = final_round and p == (self.n_players - 1)
        return UndertowState(
            tuple(sorted(deck)), tuple(wreck), undertow,
            tuple(tuple(h) for h in hauls), tuple(tuple(h) for h in holds),
            (p + 1) % self.n_players, final_round, over,
        )

    def is_terminal(self, s: UndertowState) -> bool:
        return s.over

    # -- scoring -------------------------------------------------------------------------
    @staticmethod
    def _points(cards: tuple[Card, ...]) -> int:
        return sum(c.rank for c in cards)

    def scores(self, s: UndertowState) -> list[float]:
        out = []
        for p in range(self.n_players):
            hold, haul = s.holds[p], s.hauls[p]
            base = self._points(hold) + self._points(haul)
            dust = (len(hold) * 1e-3                       # most cards in Hold
                    + (max((c.rank for c in hold), default=0)) * 1e-5   # best single Hold card
                    + (13 - min(len(haul), 13)) * 1e-7     # fewest cards left in the Haul
                    + p * 1e-9)                            # later seats win the last tie
            out.append(base + dust)
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: UndertowState, p: int) -> dict:
        """Everything is public in Undertow; only the order of the face-down deck is unknown."""
        return {
            "seat": p,
            "undertow": str(s.undertow) if s.undertow else None,
            "haul": [str(c) for c in s.hauls[p]],
            "bust_ranks": sorted(self._bust_ranks(s, p)),
            "hauls": [[str(c) for c in h] for h in s.hauls],
            "hold_points": [self._points(h) for h in s.holds],
            "hold_sizes": [len(h) for h in s.holds],
            "wreck_top": str(s.wreck[-1]) if s.wreck else None,
            "wreck_size": len(s.wreck),
            "deck_size": len(s.deck),
            "deck_ranks_left": sorted(c.rank for c in s.deck),
            "final_round": s.final_round,
            "to_move": s.current,
        }

    def describe(self, s: UndertowState) -> str:
        pts = [int(self._points(s.holds[i]) + self._points(s.hauls[i])) for i in range(self.n_players)]
        hauls = " | ".join(" ".join(str(c) for c in h) or "-" for h in s.hauls)
        return (
            f"undertow={s.undertow or '-'} deck={len(s.deck)} wreck={len(s.wreck)}"
            f"(top {s.wreck[-1] if s.wreck else '-'}) scores={pts}"
            f"{' FINAL' if s.final_round else ''}; seat {s.current} to move; hauls: {hauls}"
        )


GAME = Undertow
