"""Weathervane — a no-follow-suit trick game where a die names the trump every trick.

RULESHEET
=========
Players: 2-4.  Components: a standard 52-card deck (no jokers) and one six-sided die.
Rank order low to high: 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K, A (aces high).
Suits are indexed for the die: 1 = Clubs, 2 = Diamonds, 3 = Hearts, 4 = Spades.
Cards are written rank + suit letter: ``7H``, ``10D``, ``AS``, ``QC``.

Setup
-----
Shuffle the deck. Seats are numbered 0..N-1 clockwise; seat 0 is the dealer. Deal the cards
one at a time clockwise starting with the player to the dealer's left (seat 1):

* 2 players: 26 cards each.
* 3 players: 17 cards each; the last undealt card is removed from the game face down. Nobody
  ever sees it.
* 4 players: 13 cards each.

Everybody starts with 0 points and 0 tricks. Seat 1 is the first **Weathervane** — the player
who rolls the die and leads.

A trick, step by step
---------------------
1. **Roll.** The Weathervane rolls the die in public. The result sets the wind:
   * **1-4** — the matching suit (Clubs, Diamonds, Hearts, Spades) is trump this trick.
   * **5 — Calm.** There is no trump this trick.
   * **6 — Gale.** The suit of the card that gets led becomes trump, and the trick's points
     are doubled. Nobody knows the trump until the lead card hits the table.
2. **Lead decision.** The Weathervane either

   * ``("play", card)`` — leads any card from hand; its suit is the led suit; or
   * ``("pass_lead",)`` — hands the lead to the player on their left. That player must lead
     (they may not pass again) and the die result stays as rolled. Passing is forbidden when
     the Weathervane holds exactly one card, i.e. on the final trick.
3. **Follow.** Going clockwise from the leader, every other player plays one card. **There is
   no obligation to follow suit or to play trump**: every card in your hand is always legal.
   The Weathervane, after passing the lead, simply plays in normal clockwise order.
4. **Resolve.** The trick is won by the highest trump played; if no trump was played, by the
   highest card of the led suit. The led card always qualifies, so there is always a winner,
   and ranks inside a suit are unique, so there is never a tie.
5. **Score, at once.** The winner scores
   ``(1 point per card in the trick) + (1 extra point per trump card in the trick)``,
   and the whole total is **doubled under a Gale**. Calm pays no trump bonus.
   Example: 4 players, roll 3 (Hearts), two Hearts in the trick -> 4 + 2 = 6 points. The same
   trick under a Gale whose led suit matches those two cards -> (4 + 2) x 2 = 12 points.
   The winner also adds one to their trick count, and the trick's number is stored as their
   "last trick won".
6. **Next trick.** The winner becomes the new Weathervane. The played cards are discarded face
   up and are out of the game.

End and scoring
---------------
Hands shrink by exactly one card per trick and nothing is ever drawn, so the game ends right
after the trick that empties every hand: 26 tricks at 2 players, 17 at 3, 13 at 4. The highest
point total wins.

**Tie-breaks.** Among players tied on points: (1) most tricks won, then (2) the latest "last
trick won". Every trick pays at least 2 points, so a tied leader must have won a trick and this
always yields exactly one winner. Implementation note: ``scores()`` returns points plus a tiny
fraction (less than 0.01) that encodes the two tie-breakers, so a higher score is always the
better result; round a score down to read the real point total.

Strategy note: the wind is public before anybody commits a card, so you always know what a
trick is worth. Feed cheap trumps into fat Gale tricks, dump dead suits when the wind is
against you, and pass the lead when leading first would only hand a trump-rich trick away.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_dice import roll_d6
from gd_gamecore import GMLike

SUIT_LETTERS = "CDHS"  # index == Suit value; die face 1..4 -> SUIT_LETTERS[face - 1]
HAND_SIZE = {2: 26, 3: 17, 4: 13}
CALM, GALE = 5, 6


def code(c: Card) -> str:
    """Compact card code, e.g. ``7H``, ``10D``, ``AS``."""
    return f"{c.rank_name}{SUIT_LETTERS[int(c.suit)]}"


def sort_key(c: Card) -> tuple[int, int]:
    return (int(c.suit), c.high_value())


@dataclass
class WeathervaneState:
    hands: list[list[Card]]
    points: list[int]
    tricks_won: list[int]
    last_trick_won: list[int]  # trick number (1-based) of the player's latest win, else 0
    trick_no: int  # 1-based number of the trick being played
    weathervane: int  # seat that rolled the die this trick
    leader: int  # seat that must lead (differs from weathervane after a pass)
    pass_used: bool
    die: int  # 1..6
    trump: int | None  # Suit value, or None (Calm, or Gale before the lead)
    gale: bool
    led_suit: int | None
    trick: list[tuple[int, Card]] = field(default_factory=list)  # (seat, card) in play order
    to_act: int = 0
    phase: str = "lead"  # "lead" | "follow" | "over"
    removed: Card | None = None  # 3 players: the hidden card taken out of the game
    discards: list[Card] = field(default_factory=list)


class Weathervane:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if n_players not in HAND_SIZE:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> WeathervaneState:
        n = self.n_players
        deck = Deck(jokers=0).shuffle(rng)
        dealt = deck.deal(n, HAND_SIZE[n])
        hands: list[list[Card]] = [[] for _ in range(n)]
        for i, h in enumerate(dealt):  # dealing starts to the dealer's left (seat 1)
            hands[(1 + i) % n] = sorted(h, key=sort_key)
        removed = deck.cards[0] if deck.cards else None  # 3 players: one card leaves the game
        s = WeathervaneState(
            hands=hands,
            points=[0] * n,
            tricks_won=[0] * n,
            last_trick_won=[0] * n,
            trick_no=1,
            weathervane=1 % n,
            leader=1 % n,
            pass_used=False,
            die=1,
            trump=None,
            gale=False,
            led_suit=None,
            removed=removed,
        )
        self._roll(s, rng)
        return s

    def _roll(self, s: WeathervaneState, rng: Random) -> None:
        """Roll the wind for a fresh trick and open the lead decision."""
        s.die = roll_d6(rng).values[0]
        s.gale = s.die == GALE
        s.trump = None if s.die >= CALM else s.die - 1  # 1..4 -> Suit 0..3
        s.led_suit = None
        s.trick = []
        s.leader = s.weathervane
        s.to_act = s.weathervane
        s.pass_used = False
        s.phase = "lead"

    def current_player(self, s: WeathervaneState) -> int:
        return s.to_act

    def legal_actions(self, s: WeathervaneState) -> list[tuple]:
        if s.phase == "over":
            return []
        acts: list[tuple] = [("play", code(c)) for c in s.hands[s.to_act]]
        if s.phase == "lead" and not s.pass_used and len(s.hands[s.to_act]) > 1:
            acts.append(("pass_lead",))
        return acts

    def step(self, state: WeathervaneState, a: tuple, rng: Random) -> WeathervaneState:
        s = copy.deepcopy(state)
        if s.phase == "over":
            raise ValueError("game is over")
        p = s.to_act
        if a == ("pass_lead",):
            if s.phase != "lead" or s.pass_used or len(s.hands[p]) <= 1:
                raise ValueError("cannot pass the lead now")
            s.pass_used = True
            s.leader = s.to_act = (p + 1) % self.n_players
            return s
        if not (isinstance(a, tuple) and len(a) == 2 and a[0] == "play"):
            raise ValueError(f"illegal action {a!r}")
        card = next((c for c in s.hands[p] if code(c) == a[1]), None)
        if card is None:
            raise ValueError(f"{a[1]} not in hand of seat {p}")
        s.hands[p].remove(card)
        s.trick.append((p, card))
        if s.phase == "lead":
            s.led_suit = int(card.suit)
            if s.gale:
                s.trump = s.led_suit  # the leader picks the trump under a Gale
            s.phase = "follow"
        if len(s.trick) == self.n_players:
            self._resolve(s, rng)
        else:
            s.to_act = (s.leader + len(s.trick)) % self.n_players
        return s

    def _resolve(self, s: WeathervaneState, rng: Random) -> None:
        trumps = [(c.high_value(), seat) for seat, c in s.trick if s.trump is not None and int(c.suit) == s.trump]
        pool = trumps or [(c.high_value(), seat) for seat, c in s.trick if int(c.suit) == s.led_suit]
        winner = max(pool)[1]
        pts = self.n_players + len(trumps)
        if s.gale:
            pts *= 2
        s.points[winner] += pts
        s.tricks_won[winner] += 1
        s.last_trick_won[winner] = s.trick_no
        s.discards.extend(c for _, c in s.trick)
        s.weathervane = winner
        if not any(s.hands):
            s.trick = []
            s.phase = "over"
            s.to_act = winner
        else:
            s.trick_no += 1
            self._roll(s, rng)

    def is_terminal(self, s: WeathervaneState) -> bool:
        return s.phase == "over"

    def scores(self, s: WeathervaneState) -> list[float]:
        """Points, plus a tie-break fraction < 0.01 (tricks won, then latest trick won)."""
        return [
            float(s.points[p]) + 1e-4 * s.tricks_won[p] + 1e-8 * s.last_trick_won[p]
            for p in range(self.n_players)
        ]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: WeathervaneState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(code(c) for c in sorted(s.hands[p], key=sort_key)),
            "phase": s.phase,
            "trick_no": s.trick_no,
            "die": s.die,
            "wind": self._wind(s),
            "trump": None if s.trump is None else SUIT_LETTERS[s.trump],
            "gale": s.gale,
            "led_suit": None if s.led_suit is None else SUIT_LETTERS[s.led_suit],
            "trick": tuple((seat, code(c)) for seat, c in s.trick),
            "weathervane": s.weathervane,
            "leader": s.leader,
            "pass_used": s.pass_used,
            "to_act": s.to_act,
            "hand_sizes": tuple(len(h) for h in s.hands),
            "points": tuple(s.points),
            "tricks_won": tuple(s.tricks_won),
            "discarded": len(s.discards),
        }

    @staticmethod
    def _wind(s: WeathervaneState) -> str:
        if s.die == GALE:
            return "gale"
        if s.die == CALM:
            return "calm"
        return f"trump {SUIT_LETTERS[s.die - 1]}"

    def describe(self, s: WeathervaneState) -> str:
        if s.phase == "over":
            return f"game over after {s.trick_no} tricks; points={s.points} tricks={s.tricks_won}"
        table = ", ".join(f"s{seat}:{code(c)}" for seat, c in s.trick) or "empty"
        return (
            f"trick {s.trick_no} die={s.die} ({self._wind(s)}) weathervane=s{s.weathervane} "
            f"leader=s{s.leader}{' (passed)' if s.pass_used else ''}; table: {table}; "
            f"to act s{s.to_act}; points={s.points} hands={[len(h) for h in s.hands]}"
        )


GAME = Weathervane
