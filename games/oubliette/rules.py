"""Oubliette — a four-card dungeon corridor for 2-4 delvers.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers), one six-sided die.

Card values
-----------
2-10 face value, Jack 11, Queen 12, King 13, Ace 14.  Black cards (spades, clubs) are
**monsters** in the corridor and **weapons** in your hand.  Red cards (hearts, diamonds) are
**gold** in the corridor and in your lair, and they can also be swung as weapons from your hand.

Setup
-----
Shuffle the deck.  Deal 4 cards face-down to each player.  Deal 4 cards face-up in a row: this
is the corridor, position 1 (the entrance) through position 4 (the deepest).  The rest is the
face-down dungeon deck.  Every player has an empty lair in front of them.  The starting player
is chosen at random; play is clockwise.

Hand limit: 6 cards.  Any action or draw that would push a hand above 6 is illegal, and forced
draws that would break the limit are skipped instead.

Corridor terms
--------------
A monster at position i is *harassed* by every black card at a lower position.  Its strength is
its rank value plus 2 for each harassing black card, so deep monsters are tougher.  A gold card
is *guarded* while any black card sits in front of it, and guarded gold cannot be looted.

Turn structure
--------------
1. **Catch-up draw.**  If your lair score (full scoring, bonuses and scars included) is strictly
   lower than every other player's score, and the dungeon deck is not empty, and you hold fewer
   than 6 cards, you must draw 1 card.
2. **Take exactly one action** (below).  If nothing is legal you pass.
3. **Refill.**  If your action removed a corridor card, slide the deeper cards one step toward
   the entrance and draw the top deck card into the deepest empty position.  With an empty deck
   the corridor simply gets shorter.

Actions
-------
* **Slay** — name one corridor monster and exactly one card from your hand.  Compare your card's
  rank value with the monster's strength.  Value >= strength wins automatically.  Otherwise the
  shortfall is s = strength - value: with s >= 6 the fight may not be attempted, with s of 1-5
  you roll the die and win if it shows strictly more than s.  Either way the played card is
  discarded.  A win puts the monster face-up in your lair as a trophy and triggers a refill.
  A loss leaves the monster in place and gives you a **scar**: the top deck card goes face-down
  into your lair (no scar if the deck is empty).
* **Loot** — take one unguarded gold card from the corridor into your hand.  Legal only with
  fewer than 6 cards in hand.  Triggers a refill.  Looted gold is a weapon, not yet points.
* **Bank** — put one card from your hand face-up in your lair.  A red card banked is gold worth
  its rank value; a black card banked is a sold hireling worth a flat 3 points.  Legal whenever
  you hold a card.
* **Rest** — draw 2 cards (or the single last card).  Legal with 4 or fewer cards in hand and at
  least 1 card in the deck.
* **Scout** — move one corridor card to the deepest occupied position; the cards behind it slide
  one step toward the entrance.  Legal with at least 2 cards in the corridor when the chosen
  card is not already the deepest.  Scouting rewires harassment and unguards gold, for you or
  for the next player.

End of the game
---------------
The moment the last deck card is drawn (catch-up, refill, rest or scar), the **final round** is
triggered.  Play continues clockwise until the player to the right of the starting player has
finished their turn, so everyone gets the same number of turns.  If the last card is drawn on
that very player's turn, the game ends when their turn ends.

*Collapse (hard limit).*  If the deck somehow survives 30 full rounds, the ceiling gives way and
the final round is triggered at once.  This guarantees the game ends.

During the final round no cards are ever drawn: Rest is illegal, catch-up draws and refills are
skipped, and a lost fight leaves no scar.  A player with no legal action passes.

Scoring
-------
* Trophy (a black card won by slaying): its rank value.
* Banked red card: its rank value.  Banked black card: 3 points.
* Each scar: -3 points.
* Pair bonus: +4 for each rank value at which you hold 2 or more face-up lair cards (trophies and
  banked cards together; scars never count).  Three or four of a rank still pay only one +4.
Cards left in hand score nothing.  Highest score wins.

Tie-break: most trophies, then highest single trophy rank, then fewest scars, then the player
furthest clockwise from the starting player (the one who acts last each round).  This
implementation folds the tie-break into ``scores`` as an epsilon smaller than 0.03 point, so the
raw lair total is always the integer part of a score.

Strategy note: red cards in hand are your best weapons but score nothing there, deep monsters are
fat trophies yet need harassment cleared or a lucky die, and pairs reward hoarding a rank while
the catch-up draw keeps the trailing delver armed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_gamecore import GMLike

HAND_LIMIT = 6
CORRIDOR = 4
DEAL = 4
REST_MAX_HAND = 4
MAX_SHORTFALL = 5
HARASS = 2
HIRELING = 3
SCAR = -3
PAIR_BONUS = 4
COLLAPSE_ROUNDS = 30

SUITS = ("S", "H", "D", "C")
RANK_CODE = {11: "J", 12: "Q", 13: "K", 14: "A"}

Card = tuple  # (value: int 2..14, suit: str)


def code(c: Card) -> str:
    """Readable card code, e.g. ``KS`` or ``10H``."""
    return f"{RANK_CODE.get(c[0], str(c[0]))}{c[1]}"


def is_black(c: Card) -> bool:
    return c[1] in ("S", "C")


def fresh_deck() -> list[Card]:
    return [(v, s) for s in SUITS for v in range(2, 15)]


@dataclass
class Lair:
    trophies: list[Card] = field(default_factory=list)
    banked: list[Card] = field(default_factory=list)
    scars: int = 0


@dataclass
class OubState:
    deck: list[Card]
    discard: list[Card]
    corridor: list[Card]
    hands: list[list[Card]]
    lairs: list[Lair]
    current: int
    start: int
    final_round: bool = False
    last_player: int | None = None
    turns: int = 0
    over: bool = False
    log: str = "start"


class Oubliette:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- setup ---------------------------------------------------------------------------
    def setup(self, rng: Random) -> OubState:
        deck = fresh_deck()
        rng.shuffle(deck)
        hands = [[deck.pop() for _ in range(DEAL)] for _ in range(self.n_players)]
        for h in hands:
            h.sort()
        corridor = [deck.pop() for _ in range(CORRIDOR)]
        start = rng.randrange(self.n_players)
        s = OubState(deck, [], corridor, hands, [Lair() for _ in range(self.n_players)], start, start)
        self._begin_turn(s)
        return s

    # -- scoring -------------------------------------------------------------------------
    def _score(self, s: OubState, p: int) -> int:
        lair = s.lairs[p]
        total = sum(c[0] for c in lair.trophies)
        total += sum(c[0] if not is_black(c) else HIRELING for c in lair.banked)
        total += SCAR * lair.scars
        ranks: dict[int, int] = {}
        for c in lair.trophies + lair.banked:
            ranks[c[0]] = ranks.get(c[0], 0) + 1
        total += PAIR_BONUS * sum(1 for n in ranks.values() if n >= 2)
        return total

    def scores(self, s: OubState) -> list[float]:
        out = []
        for p in range(self.n_players):
            lair = s.lairs[p]
            best = max((c[0] for c in lair.trophies), default=0)
            dist = (p - s.start) % self.n_players
            eps = (
                len(lair.trophies) * 1e-3
                + best * 1e-5
                + (26 - lair.scars) * 1e-7
                + dist * 1e-9
            )
            out.append(float(self._score(s, p)) + eps)
        return out

    # -- corridor helpers ----------------------------------------------------------------
    def _strength(self, s: OubState, i: int) -> int:
        c = s.corridor[i]
        return c[0] + HARASS * sum(1 for j in range(i) if is_black(s.corridor[j]))

    def _guarded(self, s: OubState, i: int) -> bool:
        return any(is_black(s.corridor[j]) for j in range(i))

    # -- draw / turn plumbing ------------------------------------------------------------
    def _draw(self, s: OubState) -> Card | None:
        """Draw one card; triggers the final round when the deck empties."""
        if s.final_round or not s.deck:
            return None
        c = s.deck.pop()
        if not s.deck:
            self._trigger_final(s)
        return c

    def _trigger_final(self, s: OubState) -> None:
        if not s.final_round:
            s.final_round = True
            s.last_player = (s.start - 1) % self.n_players

    def _begin_turn(self, s: OubState) -> None:
        p = s.current
        if s.final_round or not s.deck or len(s.hands[p]) >= HAND_LIMIT:
            return
        mine = self._score(s, p)
        if all(mine < self._score(s, q) for q in range(self.n_players) if q != p):
            c = self._draw(s)
            if c is not None:
                s.hands[p].append(c)
                s.hands[p].sort()

    def _end_turn(self, s: OubState) -> None:
        p = s.current
        s.turns += 1
        if s.turns >= COLLAPSE_ROUNDS * self.n_players:
            self._trigger_final(s)
        if s.final_round and p == s.last_player:
            s.over = True
            return
        s.current = (p + 1) % self.n_players
        self._begin_turn(s)

    def _refill(self, s: OubState, i: int) -> Card:
        """Remove corridor card i, close the gap, then top up the deepest slot."""
        c = s.corridor.pop(i)
        new = self._draw(s)
        if new is not None:
            s.corridor.append(new)
        return c

    # -- protocol ------------------------------------------------------------------------
    def current_player(self, s: OubState) -> int:
        return s.current

    def legal_actions(self, s: OubState) -> list[tuple]:
        if s.over:
            return []
        p = s.current
        hand = s.hands[p]
        acts: list[tuple] = []
        for i, c in enumerate(s.corridor):
            if is_black(c):
                st = self._strength(s, i)
                for h in hand:
                    if st - h[0] <= MAX_SHORTFALL:
                        acts.append(("slay", i, code(h)))
            elif len(hand) < HAND_LIMIT and not self._guarded(s, i):
                acts.append(("loot", i))
        acts += [("bank", code(h)) for h in hand]
        if not s.final_round and s.deck and len(hand) <= REST_MAX_HAND:
            acts.append(("rest",))
        if len(s.corridor) >= 2:
            acts += [("scout", i) for i in range(len(s.corridor) - 1)]
        return acts or [("pass",)]

    def step(self, state: OubState, a: tuple, rng: Random) -> OubState:
        s = copy.deepcopy(state)
        if s.over:
            raise ValueError("game over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        p = s.current
        kind = a[0]
        if kind == "slay":
            i = a[1]
            weapon = next(h for h in s.hands[p] if code(h) == a[2])
            s.hands[p].remove(weapon)
            s.discard.append(weapon)
            short = self._strength(s, i) - weapon[0]
            win = short <= 0 or rng.randint(1, 6) > short
            if win:
                monster = self._refill(s, i)
                s.lairs[p].trophies.append(monster)
                s.log = f"seat {p} slew {code(monster)} with {a[2]}"
            else:
                scar = self._draw(s)
                if scar is not None:
                    s.discard.append(scar)
                    s.lairs[p].scars += 1
                s.log = f"seat {p} lost to {code(s.corridor[i])} using {a[2]}"
        elif kind == "loot":
            gold = self._refill(s, a[1])
            s.hands[p].append(gold)
            s.hands[p].sort()
            s.log = f"seat {p} looted {code(gold)}"
        elif kind == "bank":
            c = next(h for h in s.hands[p] if code(h) == a[1])
            s.hands[p].remove(c)
            s.lairs[p].banked.append(c)
            s.log = f"seat {p} banked {a[1]}"
        elif kind == "rest":
            for _ in range(2):
                if len(s.hands[p]) >= HAND_LIMIT:
                    break
                c = self._draw(s)
                if c is None:
                    break
                s.hands[p].append(c)
            s.hands[p].sort()
            s.log = f"seat {p} rested"
        elif kind == "scout":
            i = a[1]
            c = s.corridor.pop(i)
            s.corridor.append(c)
            s.log = f"seat {p} scouted {code(c)} to the back"
        else:
            s.log = f"seat {p} passed"
        self._end_turn(s)
        return s

    def is_terminal(self, s: OubState) -> bool:
        return s.over

    # -- views ---------------------------------------------------------------------------
    def _public_lair(self, s: OubState, p: int) -> dict:
        lair = s.lairs[p]
        return {
            "trophies": tuple(code(c) for c in lair.trophies),
            "banked": tuple(code(c) for c in lair.banked),
            "scars": lair.scars,
            "score": self._score(s, p),
        }

    def observe(self, s: OubState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(code(c) for c in s.hands[p]),
            "corridor": tuple(
                (code(c), self._strength(s, i) if is_black(c) else 0, self._guarded(s, i))
                for i, c in enumerate(s.corridor)
            ),
            "deck": len(s.deck),
            "discard": len(s.discard),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "lairs": tuple(self._public_lair(s, q) for q in range(self.n_players)),
            "current": s.current,
            "start": s.start,
            "final_round": s.final_round,
            "last_event": s.log,
        }

    def describe(self, s: OubState) -> str:
        cor = " | ".join(
            f"{code(c)}{'*' + str(self._strength(s, i)) if is_black(c) else ('(guarded)' if self._guarded(s, i) else '')}"
            for i, c in enumerate(s.corridor)
        ) or "empty"
        sc = [self._score(s, q) for q in range(self.n_players)]
        return (
            f"turn {s.turns} seat {s.current} to act{' (FINAL ROUND)' if s.final_round else ''}; "
            f"corridor: {cor}; deck={len(s.deck)}; hands={[len(h) for h in s.hands]}; scores={sc}; {s.log}"
        )


GAME = Oubliette
