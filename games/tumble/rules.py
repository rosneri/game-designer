"""Tumble — a trick-taking game where a single die sets the mode and the leader may flip it.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers) and one six-sided die.

Ranks, low to high: 2 3 4 5 6 7 8 9 10 J Q K A.  Suits: clubs C, diamonds D, hearts H,
spades S (written 7H, 10S, QC, ...).

Die faces
---------
Each face names a trick mode:
  1 = clubs are trump      2 = diamonds are trump   3 = no trump, high card wins
  4 = Undertow: no trump, low card wins             5 = hearts are trump   6 = spades are trump
Opposite faces are 1/6, 2/5 and 3/4. Flipping the die replaces its face with the opposite face
(new face = 7 - old face).

Setup
-----
Seat 0 is the dealer, play is clockwise (seat 0, seat 1, ...). Shuffle and deal 13 cards to
each player. The rest is a face-down draw pile: 26 cards with 2 players, 13 cards with
3 players, 0 cards with 4 players. All scores and trick counts start at 0. Seat 1, the player
to the dealer's left, leads the first trick (with 2 players seat 1 is the non-dealer).

Playing a trick
---------------
1. **Roll.** The die is rolled. That face is the provisional mode.
2. **Keep or Flip.** The leader chooses Keep or Flip. Flip turns the die to its opposite face.
   The resulting face is the trick's final mode and cannot change again.
3. **Lead.** The leader plays any one card face up. Its suit is the led suit.
4. **Follow.** Clockwise, every other player who still holds cards plays any one card. There is
   never an obligation to follow suit or to play trump. A player with an empty hand is skipped.
5. **Winner.**
   * Trump mode (1, 2, 5, 6): if any trump-suit card was played, the highest trump wins;
     otherwise the highest card of the led suit wins.
   * High mode (3): the highest card of the led suit wins.
   * Undertow (4): the lowest card of the led suit wins.
   A card of neither the trump suit nor the led suit can never win. Cards are unique, so a
   trick is never tied.
6. **Score.** The winner scores the trick value at once: in trump mode 1 plus the number of
   trump-suit cards played in the trick, in High mode and Undertow 1. The winner also adds 1 to
   their trick count. The played cards are set aside face down and leave the game.
7. **Draw.** If the draw pile is not empty, players draw one card each, starting with the player
   to the winner's left and going clockwise, the winner drawing last. Drawing stops the moment
   the pile runs out, so hands may become uneven.
8. The winner of the trick leads the next trick. (Clarification: if that winner has no cards
   left, the lead passes clockwise to the next player who still holds cards; that player makes
   the Keep/Flip choice.)

Game end
--------
The game ends right after the trick that empties the last hand, i.e. when every hand and the
draw pile are empty. Exactly 52 cards are played in every game.

Winner
------
Highest score wins. Among tied players, in order: most tricks won; then the tied player who
won the most recent trick; then, if none of them won a trick, the tied player closest clockwise
to the dealer's left. This always yields a single winner.

Strategy
--------
Trump tricks are the fat ones, because every trump card in them adds a point, so a flip into
your long suit can turn a cheap trick into a rich one. Undertow rewards keeping small cards of
a suit you can lead, and since nobody must follow suit, a lead into a mode your opponents
cannot answer is often worth more than a high card.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_dice import roll_d6
from gd_gamecore import GMLike

HAND = 13
TRUMP_OF = {1: Suit.CLUBS, 2: Suit.DIAMONDS, 5: Suit.HEARTS, 6: Suit.SPADES}
MODE_NAME = {1: "clubs trump", 2: "diamonds trump", 3: "high card", 4: "undertow",
             5: "hearts trump", 6: "spades trump"}
SUIT_LETTER = "CDHS"


def code(c: Card) -> str:
    """Short card code, e.g. '7H', '10S', 'QC'."""
    return f"{c.rank_name}{SUIT_LETTER[int(c.suit)]}"


@dataclass
class TumbleState:
    hands: list[list[Card]]
    pile: list[Card]
    points: list[int]
    tricks_won: list[int]
    last_win: list[int]  # index of the last trick each player won, -1 if none
    leader: int
    to_act: int
    phase: str  # "flip" | "play" | "done"
    die: int
    trick: list[tuple[int, Card]] = field(default_factory=list)
    trick_index: int = 0
    dealer: int = 0


class Tumble:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # ---------------------------------------------------------------- lifecycle
    def setup(self, rng: Random) -> TumbleState:
        deck = Deck(jokers=0).shuffle(rng)
        hands = [sorted(h) for h in deck.deal(self.n_players, HAND)]
        n = self.n_players
        leader = 1 % n
        return TumbleState(
            hands=hands, pile=list(deck.cards), points=[0] * n, tricks_won=[0] * n,
            last_win=[-1] * n, leader=leader, to_act=leader, phase="flip",
            die=roll_d6(rng).values[0],
        )

    def current_player(self, s: TumbleState) -> int:
        return s.to_act

    def legal_actions(self, s: TumbleState) -> list[tuple]:
        if s.phase == "flip":
            return [("keep",), ("flip",)]
        return [("play", code(c)) for c in s.hands[s.to_act]]

    def step(self, s: TumbleState, a, rng: Random) -> TumbleState:
        s = copy.deepcopy(s)
        if s.phase == "flip":
            if a == ("flip",):
                s.die = 7 - s.die
            elif a != ("keep",):
                raise ValueError(f"illegal action {a}")
            s.phase = "play"
            return s
        if s.phase != "play" or not isinstance(a, tuple) or len(a) != 2 or a[0] != "play":
            raise ValueError(f"illegal action {a}")
        p = s.to_act
        hand = s.hands[p]
        idx = next((i for i, c in enumerate(hand) if code(c) == a[1]), None)
        if idx is None:
            raise ValueError(f"{a[1]} not in hand of seat {p}")
        s.trick.append((p, hand.pop(idx)))
        nxt = self._next_actor(s, p)
        if nxt is None:
            self._resolve(s, rng)
        else:
            s.to_act = nxt
        return s

    def _next_actor(self, s: TumbleState, p: int) -> int | None:
        """Next clockwise player of this trick who has not played yet and holds cards."""
        played = {q for q, _ in s.trick}
        for off in range(1, self.n_players):
            q = (p + off) % self.n_players
            if q not in played and s.hands[q]:
                return q
        return None

    # ---------------------------------------------------------------- resolution
    def _resolve(self, s: TumbleState, rng: Random) -> None:
        led = s.trick[0][1].suit
        trump = TRUMP_OF.get(s.die)
        if trump is not None and any(c.suit == trump for _, c in s.trick):
            w = max((pc for pc in s.trick if pc[1].suit == trump), key=lambda pc: pc[1].high_value())[0]
        else:
            same = [pc for pc in s.trick if pc[1].suit == led]
            pick = min if s.die == 4 else max
            w = pick(same, key=lambda pc: pc[1].high_value())[0]
        value = 1 + (sum(1 for _, c in s.trick if c.suit == trump) if trump is not None else 0)
        s.points[w] += value
        s.tricks_won[w] += 1
        s.last_win[w] = s.trick_index
        s.trick = []
        s.trick_index += 1
        for off in range(1, self.n_players + 1):  # winner's left first, winner last
            if not s.pile:
                break
            s.hands[(w + off) % self.n_players].append(s.pile.pop(0))
        for h in s.hands:
            h.sort()
        if not any(s.hands):
            s.phase, s.to_act, s.leader = "done", w, w
            return
        leader = next((w + off) % self.n_players for off in range(self.n_players) if s.hands[(w + off) % self.n_players])
        s.leader = s.to_act = leader
        s.phase = "flip"
        s.die = roll_d6(rng).values[0]

    def is_terminal(self, s: TumbleState) -> bool:
        return s.phase == "done"

    def scores(self, s: TumbleState) -> list[float]:
        """Trick points; at the end a fraction < 1/2 encodes the rulesheet tie-break."""
        pts = [float(v) for v in s.points]
        if s.phase != "done":
            return pts
        n = self.n_players
        keys = [(s.points[p], s.tricks_won[p], s.last_win[p], -((p - s.dealer - 1) % n)) for p in range(n)]
        order = sorted(range(n), key=lambda p: keys[p])  # worst first; keys are distinct
        for rank, p in enumerate(order):
            pts[p] += rank / (2 * n)
        return pts

    # ---------------------------------------------------------------- views
    def observe(self, s: TumbleState, p: int) -> dict:
        return {
            "seat": p,
            "hand": [code(c) for c in s.hands[p]],
            "die": s.die,
            "mode": MODE_NAME[s.die],
            "phase": s.phase,
            "leader": s.leader,
            "to_act": s.to_act,
            "trick": [(q, code(c)) for q, c in s.trick],
            "points": list(s.points),
            "tricks_won": list(s.tricks_won),
            "hand_sizes": [len(h) for h in s.hands],
            "pile": len(s.pile),
            "trick_index": s.trick_index,
        }

    def describe(self, s: TumbleState) -> str:
        table = " ".join(f"{q}:{code(c)}" for q, c in s.trick) or "-"
        return (
            f"trick {s.trick_index + 1} die={s.die} ({MODE_NAME[s.die]}) phase={s.phase} "
            f"leader=seat {s.leader} to_act=seat {s.to_act}; table: {table}; "
            f"points={s.points} tricks={s.tricks_won} hands={[len(h) for h in s.hands]} pile={len(s.pile)}"
        )


GAME = Tumble
