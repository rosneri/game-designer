"""Barrow — raid a torchlit hall of monsters and loot.

RULESHEET
=========
Players: 2-4.  Components: one 52-card deck, one six-sided die.  No jokers.

Card values: Ace = 14, King = 13, Queen = 12, Jack = 11, others face value.
In the hall, black cards (spades, clubs) are **monsters** and red cards (hearts, diamonds) are
**loot**. A card in your hand is whatever you make of it: a weapon to swing, or a treasure to
stash.

Setup
-----
Shuffle the deck. Deal 2 cards to each player as a hidden hand. Reveal 3 cards face up in a row:
this is the **hall** (kept in reveal order, oldest at the left). Then count the rest of the deck
down to the barrow's depth and seal the surplus away face down, unused for the whole game:

    2 players: 30 cards      3 players: 33 cards      4 players: 36 cards

That is exactly 15 / 11 / 9 rounds of play. Each player keeps a **lair**: a face-down pile that
only its owner may look at. Choose a start player at random; play goes clockwise.

Hall limit
----------
The hall holds at most 6 cards. If a card is revealed into a full hall, the oldest hall card
**flees**: it and any hoard beneath it leave the game before the new card is placed.

Hoards
------
A monster may have a **hoard**: face-up cards stacked beneath it. A monster's strength is its
value plus the number of cards in its hoard. Loot never has a hoard.

A turn
------
1. **Reveal.** If the barrow deck is not empty, turn its top card face up into the right end of
   the hall (apply the hall limit first). If the deck is empty, skip this step.
2. **Act.** Take exactly one action:

   * **Grab** — take one loot (red) card from the hall into your hand. Not allowed with 5 cards
     in hand.
   * **Fight** — name one monster in the hall and one card of your hand as your weapon, then
     roll the die. Attack = weapon value + die + foe bonus. The foe bonus is +3 when the weapon
     suit answers the monster suit: hearts or clubs against spades, diamonds or spades against
     clubs; otherwise 0. If attack >= the monster's strength you win: the monster and its whole
     hoard go face down into your lair, and the weapon is spent (out of the game). If attack is
     lower you lose: the weapon goes face up onto that monster's hoard, so its strength rises
     by 1 for the next raider.
   * **Stash** — put one card from your hand face down into your lair. Safe points, no risk.
   * **Forage** — take the top card of the barrow deck into your hand without showing it. Not
     allowed with an empty deck or with 5 cards in hand.
   * **Pass** — only when no other action is legal.

End of the game
---------------
When the barrow deck is empty at the end of a full round (that is, after the turn of the seat
to the right of the start player), the game ends. Every player has had the same number of turns.
Cards in the hall and in hands score nothing.

Scoring
-------
Add the values of every card in your lair: monsters, the hoard cards you captured with them, and
the cards you stashed. Then add **5 points for each rank at which your lair holds both the spade
and the club** of that rank.

Tie-breaks, in order: more black cards in the lair; then the highest single black card in the
lair (a spade beats the club of the same rank); then the tied player who acted later in the
final round (farther clockwise from the start player).

Worked turn
-----------
Hall (oldest first): 9(spades) with a hoard of 4(diamonds); K(hearts); 6(clubs). Ada holds
Q(hearts) and 3(spades); the barrow deck still has cards.
Reveal: the top card is 2(spades) and joins the right end -> hall is 9(spades)+hoard, K(hearts),
6(clubs), 2(spades).
Ada's options include grabbing K(hearts), stashing either card, foraging, or eight different
fights. She fights the 9 of spades with Q(hearts): the monster's strength is 9 + 1 hoard card =
10; her attack is 12 (queen) + die + 3 (hearts answer spades). Any roll wins, so she takes
9(spades) and 4(diamonds) into her lair (9 + 4 = 13 points) and the queen is spent. Had she
swung the 3 of spades instead, her attack would be 3 + die + 0 = 4..9 < 10, a certain loss that
would drop the 3 of spades onto the hoard and make the monster strength 11.

Worked scoring
--------------
Ben's lair at the end holds K(spades), K(clubs), 4(diamonds) (hoard captured with a king),
7(spades) and A(hearts) (stashed). Card values: 13 + 13 + 4 + 7 + 14 = 51, plus 5 for holding
both kings in black = **56**. Ada's lair holds A(spades), 9(spades), 4(diamonds), Q(diamonds)
and 8(hearts): 14 + 9 + 4 + 12 + 8 = 47, no black pair = **47**. Ben wins. Had Ada also reached
56, she would win the tie only with more black cards (she has 2 to Ben's 3, so Ben still wins).

Strategy note: a stashed 8 is 8 sure points, but the same 8 swung at a hoarded monster can be
worth 20 — and a failed swing feeds the monster you were trying to rob.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Suit, standard_deck
from gd_gamecore import GMLike

HAND_LIMIT = 5
HALL_LIMIT = 6
START_HAND = 2
START_HALL = 3
FOE_BONUS = 3
# Barrow depth: deck size per player count == rounds * n_players (15 / 11 / 9 rounds).
DEPTH = {2: 30, 3: 33, 4: 36}
# weapon suit -> monster suit it answers for the +3 foe bonus
FOE: dict[int, tuple[int, ...]] = {
    Suit.SPADES: (Suit.HEARTS, Suit.CLUBS),
    Suit.CLUBS: (Suit.DIAMONDS, Suit.SPADES),
}


def value(c: Card) -> int:
    """Ace 14, King 13, Queen 12, Jack 11, else face value."""
    return c.high_value()


def is_black(c: Card) -> bool:
    return Suit(c.suit) in (Suit.SPADES, Suit.CLUBS)


@dataclass
class HallCard:
    """A face-up hall card; ``hoard`` is non-empty only for monsters that beat someone."""

    card: Card
    hoard: list[Card] = field(default_factory=list)

    @property
    def strength(self) -> int:
        return value(self.card) + len(self.hoard)


@dataclass
class BarrowState:
    deck: list[Card]
    hall: list[HallCard]
    hands: list[list[Card]]
    lairs: list[list[Card]]
    start: int
    cur: int
    turns: int = 0
    ended: bool = False
    log: str = "the barrow is opened"


class Barrow:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm
        self.max_turns = DEPTH[n_players]  # deck size == rounds * n_players

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> BarrowState:
        deck = standard_deck()
        rng.shuffle(deck)
        hands = [[deck.pop() for _ in range(START_HAND)] for _ in range(self.n_players)]
        for h in hands:
            h.sort()
        hall = [HallCard(deck.pop()) for _ in range(START_HALL)]
        deck = deck[: DEPTH[self.n_players]]  # seal the surplus away, unused
        start = rng.randrange(self.n_players)
        s = BarrowState(deck, hall, hands, [[] for _ in range(self.n_players)], start, start)
        self._reveal(s)  # the first player's own reveal step
        return s

    def current_player(self, s: BarrowState) -> int:
        return s.cur

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: BarrowState) -> list[tuple]:
        hand = s.hands[s.cur]
        acts: list[tuple] = []
        if len(hand) < HAND_LIMIT:
            acts += [("grab", str(e.card)) for e in s.hall if not is_black(e.card)]
        for e in s.hall:
            if is_black(e.card):
                acts += [("fight", str(e.card), str(w)) for w in hand]
        acts += [("stash", str(w)) for w in hand]
        if s.deck and len(hand) < HAND_LIMIT:
            acts.append(("forage",))
        return acts or [("pass",)]

    def step(self, s: BarrowState, a: tuple, rng: Random) -> BarrowState:
        if self.is_terminal(s):
            raise ValueError("game over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        p = s.cur
        kind = a[0]
        if kind == "grab":
            e = self._hall_entry(s, a[1])
            s.hall.remove(e)
            s.hands[p].append(e.card)
            s.log = f"seat {p} grabbed {e.card}"
        elif kind == "fight":
            s.log = self._fight(s, p, self._hall_entry(s, a[1]), self._hand_card(s, p, a[2]), rng)
        elif kind == "stash":
            c = self._hand_card(s, p, a[1])
            s.hands[p].remove(c)
            s.lairs[p].append(c)
            s.log = f"seat {p} stashed a card"
        elif kind == "forage":
            s.hands[p].append(s.deck.pop(0))
            s.log = f"seat {p} foraged"
        else:
            s.log = f"seat {p} passed"
        s.hands[p].sort()

        s.turns += 1
        end_of_round = s.turns % self.n_players == 0
        if (end_of_round and not s.deck) or s.turns >= self.max_turns:
            s.ended = True
            return s
        s.cur = (s.cur + 1) % self.n_players
        self._reveal(s)
        return s

    def _hall_entry(self, s: BarrowState, code: str) -> HallCard:
        return next(e for e in s.hall if str(e.card) == code)

    def _hand_card(self, s: BarrowState, p: int, code: str) -> Card:
        return next(c for c in s.hands[p] if str(c) == code)

    def _reveal(self, s: BarrowState) -> None:
        if not s.deck:
            return
        if len(s.hall) >= HALL_LIMIT:
            fled = s.hall.pop(0)  # the oldest card flees with its hoard
            s.log += f"; {fled.card} fled the hall"
        s.hall.append(HallCard(s.deck.pop(0)))

    def _fight(self, s: BarrowState, p: int, e: HallCard, w: Card, rng: Random) -> str:
        s.hands[p].remove(w)
        die = rng.randint(1, 6)
        bonus = FOE_BONUS if Suit(e.card.suit) in FOE.get(Suit(w.suit), ()) else 0
        attack = value(w) + die + bonus
        if attack >= e.strength:
            s.hall.remove(e)
            s.lairs[p] += [e.card, *e.hoard]
            return f"seat {p} rolled {die}, attack {attack} beat {e.card} ({e.strength})"
        e.hoard.append(w)
        return f"seat {p} rolled {die}, attack {attack} failed against {e.card} ({e.strength - 1})"

    # -- results -------------------------------------------------------------------------
    def is_terminal(self, s: BarrowState) -> bool:
        return s.ended

    def _points(self, lair: list[Card]) -> int:
        pts = sum(value(c) for c in lair)
        spades = {c.rank for c in lair if Suit(c.suit) == Suit.SPADES}
        clubs = {c.rank for c in lair if Suit(c.suit) == Suit.CLUBS}
        return pts + 5 * len(spades & clubs)

    def scores(self, s: BarrowState) -> list[float]:
        """Lair points; tiny nested terms encode the tie-break chain so a game never ends drawn."""
        out = []
        for p, lair in enumerate(s.lairs):
            blacks = [c for c in lair if is_black(c)]
            top = max((value(c) * 2 + (Suit(c.suit) == Suit.SPADES) for c in blacks), default=0)
            seat = (p - s.start) % self.n_players  # later in the final round wins the last tie
            out.append(self._points(lair) + 1e-3 * len(blacks) + 2e-5 * top + 1e-6 * seat)
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: BarrowState, p: int) -> tuple:
        return (
            ("hand", tuple(str(c) for c in s.hands[p])),
            ("lair", tuple(str(c) for c in s.lairs[p]), self._points(s.lairs[p])),
            ("hall", tuple((str(e.card), e.strength, tuple(str(c) for c in e.hoard)) for e in s.hall)),
            ("deck", len(s.deck)),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("lair_sizes", tuple(len(l) for l in s.lairs)),
            ("turn", s.turns, "start", s.start, "to_act", s.cur),
            ("log", s.log),
        )

    def describe(self, s: BarrowState) -> str:
        hall = " | ".join(f"{e.card}({e.strength})" + ("+" * len(e.hoard)) for e in s.hall) or "empty"
        state = "ended" if s.ended else f"seat {s.cur} to act"
        return (
            f"turn {s.turns}/{self.max_turns}, deck {len(s.deck)}, {state}; hall: {hall}; "
            f"hands={[len(h) for h in s.hands]} lairs={[len(l) for l in s.lairs]} "
            f"points={[self._points(l) for l in s.lairs]}; last: {s.log}"
        )


GAME = Barrow
