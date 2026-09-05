"""Lamplighter — a memory-and-matching gallery game.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck, no jokers, no dice.
Card values: A = 1, 2-10 = face value, J = 11, Q = 12, K = 13.

Setup
-----
Shuffle the deck. Deal 14 cards face-down into a **sealed vault**; nobody looks at it during
play, and it is only unsealed when the gallery closes. Deal 6 cards face-down as the
**gallery**: row A (positions A1, A2, A3) and row B (positions B1, B2, B3). Deal each player a
secret hand of 3 cards. The rest is the face-down **draw pile**. The discard pile starts empty,
and each player has an empty face-up **score pile** (their wall). The start player is chosen at
random; play goes clockwise.

Knowledge
---------
Gallery cards hang face-down. You know a gallery card only if you peeked at it, or if it was
publicly revealed or publicly placed at that position, and the position has not been refilled
or rehung since. Memory is the whole game; nobody may take notes.

Wall limit
----------
Your wall holds at most **5 claimed paintings**. Once you have claimed 5, you may no longer
claim; you may still peek and rehang. Choose your five paintings well.

Turn — take exactly one action
------------------------------
1. **Peek (position).** Look privately at the card at an occupied gallery position and put it
   back face-down. Nothing else happens. Safe, and nobody learns what you saw.

2. **Claim (hand card, position).** Legal only while your wall holds fewer than 5 paintings.
   Turn the card at an occupied position face-up so everybody sees it, then compare it with
   your played card. The painting always comes down onto your wall and scores its value; the
   match decides what happens to your own card.
   * **Rank match** (same rank): your played card joins the painting on your wall, so the
     claim scores twice the rank value. The position is refilled face-down from the top of the
     draw pile; if the draw pile is empty the position stays empty.
   * **Suit match** (same suit, different rank): the painting scores its value and your played
     card is hung face-down in the vacated position — but everybody saw it, so everybody now
     knows what hangs there and can claim it next.
   * **No match**: the painting still scores its value, but your played card is wasted on the
     discard pile and the position is refilled face-down from the draw pile.

3. **Rehang (row, position in that row).** Choose row A or row B containing at least one card.
   Gather its face-down cards, shuffle them blind, and deal them back face-down into the same
   occupied positions in random order. Everybody (including you) loses all knowledge of that
   row. Then peek privately at the card now in the position you chose, and put it back. A row
   of one card is a legal rehang and still gives you the peek.

End of turn
-----------
If you hold fewer than 3 cards and the draw pile is not empty, draw until you hold 3 or the
pile runs out. Then play passes to the left.

Ending the game
---------------
The gallery closes as soon as any of these happens at the end of a turn: every player's wall is
full, the gallery is completely empty, or the final stretch runs out. The **final stretch**
starts when the draw pile becomes empty: play continues until the player to the right of the
start player has completed their turn, and then one further full round is played. Hands are no
longer refilled; a player with an empty hand may still Peek or Rehang. A safety limit also
closes the gallery after 40 turns per player.

Closing by lot
--------------
When the gallery closes, the sealed vault is unsealed and its 14 paintings are hung by lot:
shuffle them and deal them out one at a time, each to a seat drawn at random, onto that
player's wall. The lots ignore the wall limit. Nobody can plan for the lots, so a modest wall
can still win the evening — but a strong wall is still the best bet.

Scoring
-------
Your score is the total value of the cards on your wall, claimed paintings and lots together.
Highest score wins. Tie-break chain: fewer cards on the wall wins (more efficient claims);
then the tied player holding the single highest-value card (comparing next-highest, and so on);
then the tied player furthest from the start player in clockwise order. In this implementation
the tie-break is folded into ``scores`` as a fraction smaller than one point, so the reported
score still shows your card total when rounded down.

Strategy
--------
Every claim pays, so the question is *which* painting and *when*: with only five claims you
want kings and rank matches, and that means lamp work. Suit matches pay once and leave your own
card hanging in plain sight for the next player. Rehang when other people know more than you do
— it costs you a claim-free turn but buys you one private look and wrecks everybody else's map
of that row. And keep an eye on the clock: the vault lots reward nobody, so a small lead is
never safe.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from gd_cards import Card, Deck
from gd_gamecore import GMLike

HAND = 3
VAULT = 14
WALL_LIMIT = 5
ROWS = {"A": ("A1", "A2", "A3"), "B": ("B1", "B2", "B3")}
POSITIONS = ROWS["A"] + ROWS["B"]
FINAL_ROUNDS = 1
TURNS_PER_PLAYER_CAP = 40


def value(c: Card) -> int:
    """Card value: A = 1, 2-10 face value, J = 11, Q = 12, K = 13."""
    return c.rank


@dataclass
class LampState:
    gallery: dict[str, Card | None]
    hands: list[list[Card]]
    draw: list[Card]
    vault: list[Card]
    discard: list[Card]
    piles: list[list[Card]]           # face-up score piles (walls)
    claims: list[int]                 # paintings claimed per player (wall limit)
    knowledge: list[dict[str, Card]]  # per player: position -> remembered card
    start: int
    turn_of: int
    turns: int = 0
    final_left: int | None = None     # turns still to play once the draw pile is empty
    over: bool = False
    log: str = "the gallery opens"
    revealed: dict[str, Any] = field(default_factory=dict)  # last public reveal (for describe)


class Lamplighter:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> LampState:
        deck = Deck(jokers=0).shuffle(rng)
        vault = deck.draw(VAULT)
        gallery = {pos: deck.draw_one() for pos in POSITIONS}
        hands = [sorted(h) for h in deck.deal(self.n_players, HAND)]
        start = rng.randrange(self.n_players)
        return LampState(
            gallery=gallery,
            hands=hands,
            draw=list(deck.cards),
            vault=vault,
            discard=[],
            piles=[[] for _ in range(self.n_players)],
            claims=[0 for _ in range(self.n_players)],
            knowledge=[{} for _ in range(self.n_players)],
            start=start,
            turn_of=start,
        )

    def current_player(self, s: LampState) -> int:
        return s.turn_of

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: LampState) -> list[tuple]:
        occupied = [p for p in POSITIONS if s.gallery[p] is not None]
        acts: list[tuple] = [("peek", p) for p in occupied]
        if s.claims[s.turn_of] < WALL_LIMIT:
            for c in s.hands[s.turn_of]:
                for p in occupied:
                    acts.append(("claim", str(c), p))
        for row, positions in ROWS.items():
            here = [p for p in positions if s.gallery[p] is not None]
            for p in here:
                acts.append(("rehang", row, p))
        return acts

    def step(self, s: LampState, a: tuple, rng: Random) -> LampState:
        if s.over:
            raise ValueError("game is over")
        if a not in set(self.legal_actions(s)):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        p = s.turn_of
        kind = a[0]
        if kind == "peek":
            pos = a[1]
            card = s.gallery[pos]
            s.knowledge[p][pos] = card
            s.revealed = {}
            s.log = f"seat {p} peeks at {pos}"
        elif kind == "claim":
            self._claim(s, p, a[1], a[2])
        else:
            self._rehang(s, p, a[1], a[2], rng)

        # end of turn: refill hand while the draw pile lasts
        while len(s.hands[p]) < HAND and s.draw:
            s.hands[p].append(s.draw.pop(0))
        s.hands[p].sort()

        s.turns += 1
        if s.final_left is None:
            if not s.draw:
                last = (s.start - 1) % self.n_players
                s.final_left = ((last - p) % self.n_players) + FINAL_ROUNDS * self.n_players
        else:
            s.final_left -= 1

        if (
            (s.final_left is not None and s.final_left <= 0)
            or all(s.gallery[q] is None for q in POSITIONS)
            or all(c >= WALL_LIMIT for c in s.claims)
            or s.turns >= TURNS_PER_PLAYER_CAP * self.n_players
        ):
            s.over = True
            self._unseal(s, rng)
        s.turn_of = (p + 1) % self.n_players
        return s

    def _claim(self, s: LampState, p: int, card_str: str, pos: str) -> None:
        played = next(c for c in s.hands[p] if str(c) == card_str)
        s.hands[p].remove(played)
        shown = s.gallery[pos]
        assert shown is not None
        for k in s.knowledge:  # the reveal is public
            k[pos] = shown
        s.piles[p].append(shown)       # the painting always comes down onto your wall
        s.claims[p] += 1
        if shown.rank == played.rank:
            s.piles[p].append(played)
            s.gallery[pos] = s.draw.pop(0) if s.draw else None
            for k in s.knowledge:
                k.pop(pos, None)
            outcome = f"rank match, scores {2 * value(shown)}"
        elif shown.suit == played.suit:
            s.gallery[pos] = played
            for k in s.knowledge:  # everybody saw the played card go up
                k[pos] = played
            outcome = f"suit match, scores {value(shown)}"
        else:
            s.discard.append(played)
            s.gallery[pos] = s.draw.pop(0) if s.draw else None
            for k in s.knowledge:
                k.pop(pos, None)
            outcome = f"no match, scores {value(shown)} and wastes {played}"
        s.revealed = {"pos": pos, "card": str(shown), "played": str(played)}
        s.log = f"seat {p} claims {pos} with {played} vs {shown}: {outcome}"

    def _rehang(self, s: LampState, p: int, row: str, pos: str, rng: Random) -> None:
        spots = [q for q in ROWS[row] if s.gallery[q] is not None]
        cards = [s.gallery[q] for q in spots]
        rng.shuffle(cards)
        for q, c in zip(spots, cards):
            s.gallery[q] = c
        for k in s.knowledge:  # the whole row becomes a mystery again
            for q in ROWS[row]:
                k.pop(q, None)
        s.knowledge[p][pos] = s.gallery[pos]
        s.revealed = {}
        s.log = f"seat {p} rehangs row {row} and peeks at {pos}"

    def _unseal(self, s: LampState, rng: Random) -> None:
        """The gallery closes: hang the sealed vault by lot, one card per random seat."""
        lots = list(s.vault)
        rng.shuffle(lots)
        s.vault = []
        for c in lots:
            s.piles[rng.randrange(self.n_players)].append(c)
        s.log += "; the vault is unsealed and hung by lot"

    # -- end -----------------------------------------------------------------------------
    def is_terminal(self, s: LampState) -> bool:
        return s.over

    def _points(self, s: LampState, p: int) -> int:
        return sum(value(c) for c in s.piles[p])

    def scores(self, s: LampState) -> list[float]:
        n = self.n_players
        keys = []
        for p in range(n):
            vals = sorted((value(c) for c in s.piles[p]), reverse=True)
            keys.append((self._points(s, p), -len(s.piles[p]), vals, (p - s.start) % n))
        order = sorted(range(n), key=lambda p: keys[p])  # worst first
        eps = {p: 0.9 * i / n for i, p in enumerate(order)}  # tie-break < 1 point
        return [float(self._points(s, p)) + eps[p] for p in range(n)]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: LampState, p: int) -> dict:
        return {
            "seat": p,
            "to_move": s.turn_of,
            "hand": tuple(str(c) for c in s.hands[p]),
            "gallery": tuple((q, s.gallery[q] is not None) for q in POSITIONS),
            "known": tuple(sorted((q, str(c)) for q, c in s.knowledge[p].items() if s.gallery[q] is not None)),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "points": tuple(self._points(s, q) for q in range(self.n_players)),
            "piles": tuple(tuple(sorted(str(c) for c in pile)) for pile in s.piles),
            "claims": tuple(s.claims),
            "wall_limit": WALL_LIMIT,
            "draw": len(s.draw),
            "vault": len(s.vault),
            "discard": tuple(str(c) for c in s.discard),
            "start": s.start,
            "final_left": s.final_left,
            "turns": s.turns,
            "last": s.log,
        }

    def describe(self, s: LampState) -> str:
        gal = " ".join(f"{q}:{'#' if s.gallery[q] else '-'}" for q in POSITIONS)
        phase = "final stretch" if s.final_left is not None else "gallery open"
        return (
            f"turn {s.turns} ({phase}"
            + (f", {s.final_left} left" if s.final_left is not None else "")
            + f") seat {s.turn_of} to move; {gal}; draw={len(s.draw)} "
            f"claims={list(s.claims)} points={[self._points(s, q) for q in range(self.n_players)]}; {s.log}"
        )


GAME = Lamplighter
