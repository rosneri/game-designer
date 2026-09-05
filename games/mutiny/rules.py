"""Mutiny — a shedding race aboard a pirate ship, ruled by two joker Orders.

RULESHEET
=========
Players: 2-4.  Components: a 52-card deck, two jokers, one six-sided die.

Ranks run 2 (low) through Ace (high): 2..10, J=11, Q=12, K=13, A=14. The two jokers are never
dealt and never held. They lie in the middle of the table as the crew's two standing **Orders**:

* **Heading joker** — upright = **CLIMB**, sideways = **DIVE**.
* **Cargo joker** — upright = **SINGLE**, sideways = **STACK**.

Hand size
---------
2 players: 7 cards.  3 players: 6 cards.  4 players: 5 cards.

Game length
-----------
Exactly 3 rounds at every player count.

Round setup
-----------
Shuffle all 52 cards. Deal each player their hand size. Turn the next card face up to start the
**Wake** (the play pile). Then count out 6 cards per player face down as the **hold** (the draw
deck); the rest of the pack is set aside unused for this round. Set both jokers upright (CLIMB
and SINGLE). In round 1 the starting player is chosen at random. In rounds 2 and 3 the starter is
the player with the lowest total score; if several tie for lowest, walk clockwise from the seat
immediately after the previous round's starter and take the first tied player found.

Legal plays
-----------
A play is a set of 1 or more cards of the **same rank** from your hand. That rank must be legal
against the current top card of the Wake:

* Under **CLIMB**: rank higher than, or equal to, the top card's rank.
* Under **DIVE**: rank lower than, or equal to, the top card's rank.

Equal rank is always legal in both headings, so a "hold" play never changes the pile height.
Under **SINGLE** a play is exactly 1 card. Under **STACK** a play is 1 to 4 cards of one rank.
You choose which card of the play ends up on top of the Wake; only that card matters afterwards.
(In this implementation an action lists the played cards with the chosen top card written last.)

Scoring a play
--------------
Score at once: 1 point per card played, plus 1 bonus point if at least one played card shares the
suit of the card it covered (the Wake's top card before the play). Scores accumulate across the
whole game and may go negative.

Your turn
---------
Take exactly one of these actions:

1. **Play.** Make one legal play and score it.
2. **Mutiny.** Name the joker you attack (Heading or Cargo), then roll the die. The mutiny
   succeeds if the roll is less than or equal to the number of cards in your hand. On success,
   flip that joker to its other state, then immediately make one legal play under the new Orders
   and score it; if no legal play exists after the flip, draw 1 card instead. On failure the
   joker does not move and you draw 1 card.

Playing is never mandatory: you may mutiny while holding a legal play. Mutiny is always
available, so every turn offers a decision. A player with 6 or more cards succeeds
automatically; a player with 1 card succeeds only on a roll of 1. The crew only listens to
players with cargo still in hand, so the leader near going out cannot change the rules.

Going out
---------
If a play empties your hand you score a 3-point bonus at once and the round ends.

Deck exhaustion
---------------
If any rule tells you to draw and the hold is empty, no card is drawn and the round ends at once.
The hold is small, so a round of failed mutinies runs out of cargo fast.

Round end
---------
Every player still holding cards loses 1 point per card in hand. If that was round 3 the game
ends; otherwise deal the next round.

Winner and tie-breaks
---------------------
Highest total score wins. Ties break in this order: (1) more rounds won by going out; (2) fewer
cards in hand at the end of round 3; (3) the tied player who made a play most recently in the
game. The final score reported by this implementation folds the tie-breaks in as tiny fractions
(always smaller than one point), so the ordering matches the rules above.

Strategy note: burning an Ace now pays 2 points, but keeping it jams the Wake at the top under
CLIMB and forces an opponent into a coin-flip mutiny.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from itertools import combinations
from random import Random

from gd_gamecore import GMLike

ROUNDS = 3
HAND_SIZES = {2: 7, 3: 6, 4: 5}
SUPPLY_PER_PLAYER = 6  # size of the "hold" (draw deck); the rest of the pack is set aside
SUITS = "CDHS"
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}

CLIMB, DIVE = "CLIMB", "DIVE"
SINGLE, STACK = "SINGLE", "STACK"
MAIN, AFTER_MUTINY, GAME_OVER = "MAIN", "AFTER_MUTINY", "GAME_OVER"

Card = tuple  # (rank: int 2..14, suit: int 0..3)


def card_str(c: Card) -> str:
    r, s = c
    return f"{RANK_NAMES.get(r, str(r))}{SUITS[s]}"


def parse_card(t: str) -> Card:
    inv = {v: k for k, v in RANK_NAMES.items()}
    return (inv.get(t[:-1], 0) or int(t[:-1]), SUITS.index(t[-1]))


def full_deck() -> list[Card]:
    return [(r, s) for s in range(4) for r in range(2, 15)]


@dataclass
class MutinyState:
    hands: list[list[Card]]
    deck: list[Card]
    wake: list[Card]
    heading: str = CLIMB
    cargo: str = SINGLE
    scores: list[int] = field(default_factory=list)
    rounds_won: list[int] = field(default_factory=list)
    rnd: int = 1
    starter: int = 0
    current: int = 0
    phase: str = MAIN
    last_play_turn: list[int] = field(default_factory=list)  # -1 = never played
    final_hand_counts: list[int] = field(default_factory=list)
    turn: int = 0
    log: str = ""


class Mutiny:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if n_players not in HAND_SIZES:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm
        self.hand_size = HAND_SIZES[n_players]

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> MutinyState:
        n = self.n_players
        s = MutinyState(
            hands=[[] for _ in range(n)],
            deck=[],
            wake=[],
            scores=[0] * n,
            rounds_won=[0] * n,
            last_play_turn=[-1] * n,
            final_hand_counts=[0] * n,
        )
        s.starter = rng.randrange(n)
        self._deal(s, rng)
        return s

    def _deal(self, s: MutinyState, rng: Random) -> None:
        deck = full_deck()
        rng.shuffle(deck)
        n = self.n_players
        s.hands = [sorted(deck[i * self.hand_size:(i + 1) * self.hand_size]) for i in range(n)]
        rest = deck[n * self.hand_size:]
        s.wake = [rest[0]]
        s.deck = rest[1:1 + SUPPLY_PER_PLAYER * n]
        s.heading, s.cargo = CLIMB, SINGLE
        s.current = s.starter
        s.phase = MAIN
        s.log = f"round {s.rnd} dealt; seat {s.starter} starts"

    # -- queries -------------------------------------------------------------------------
    def current_player(self, s: MutinyState) -> int:
        return s.current

    def _rank_ok(self, s: MutinyState, rank: int) -> bool:
        top = s.wake[-1][0]
        return rank >= top if s.heading == CLIMB else rank <= top

    def _plays(self, s: MutinyState, p: int) -> list[tuple]:
        hand = s.hands[p]
        by_rank: dict[int, list[Card]] = {}
        for c in hand:
            by_rank.setdefault(c[0], []).append(c)
        out: list[tuple] = []
        for rank, cards in sorted(by_rank.items()):
            if not self._rank_ok(s, rank):
                continue
            cards = sorted(cards)
            sizes = [1] if s.cargo == SINGLE else range(1, len(cards) + 1)
            for k in sizes:
                for combo in combinations(cards, k):
                    for top in combo:
                        rest = [c for c in combo if c != top]
                        out.append(("play",) + tuple(card_str(c) for c in rest) + (card_str(top),))
        return out

    def legal_actions(self, s: MutinyState) -> list[tuple]:
        if s.phase == GAME_OVER:
            return []
        p = s.current
        plays = self._plays(s, p)
        if s.phase == AFTER_MUTINY:
            return plays  # non-empty: the engine never enters this phase without a play
        return plays + [("mutiny", "heading"), ("mutiny", "cargo")]

    def is_terminal(self, s: MutinyState) -> bool:
        return s.phase == GAME_OVER

    def scores(self, s: MutinyState) -> list[float]:
        n = self.n_players
        # tie-breaks folded in as fractions well below one point
        order = sorted(range(n), key=lambda p: s.last_play_turn[p])
        recency = {p: i for i, p in enumerate(order)}
        max_cards = max(self.hand_size, 1)
        return [
            float(s.scores[p])
            + 1e-3 * s.rounds_won[p]
            + 1e-6 * (max_cards - s.final_hand_counts[p])
            + 1e-9 * recency[p]
            for p in range(n)
        ]

    # -- transitions ---------------------------------------------------------------------
    def step(self, s: MutinyState, a: tuple, rng: Random) -> MutinyState:
        if self.is_terminal(s):
            raise ValueError("game over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        s.turn += 1
        p = s.current
        if a[0] == "play":
            self._do_play(s, p, [parse_card(t) for t in a[1:]], rng)
            return s
        # mutiny
        joker = a[1]
        roll = rng.randint(1, 6)
        if roll <= len(s.hands[p]):
            if joker == "heading":
                s.heading = DIVE if s.heading == CLIMB else CLIMB
            else:
                s.cargo = STACK if s.cargo == SINGLE else SINGLE
            s.log = f"seat {p} mutiny {joker} rolled {roll}: success ({s.heading}/{s.cargo})"
            if self._plays(s, p):
                s.phase = AFTER_MUTINY
                return s
            s.log += "; no legal play, draws"
            self._draw_or_end(s, p, rng)
            return s
        s.log = f"seat {p} mutiny {joker} rolled {roll}: failed, draws"
        self._draw_or_end(s, p, rng)
        return s

    def _do_play(self, s: MutinyState, p: int, cards: list[Card], rng: Random) -> None:
        covered = s.wake[-1]
        for c in cards:
            s.hands[p].remove(c)
        s.wake.extend(cards)
        gain = len(cards) + (1 if any(c[1] == covered[1] for c in cards) else 0)
        s.scores[p] += gain
        s.last_play_turn[p] = s.turn
        s.phase = MAIN
        s.log = f"seat {p} played {' '.join(card_str(c) for c in cards)} for {gain}"
        if not s.hands[p]:
            s.scores[p] += 3
            s.rounds_won[p] += 1
            s.log += "; went out (+3), round over"
            self._end_round(s, rng)
        else:
            self._advance(s)

    def _draw_or_end(self, s: MutinyState, p: int, rng: Random) -> None:
        s.phase = MAIN
        if not s.deck:
            s.log += "; deck empty, round over"
            self._end_round(s, rng)
            return
        s.hands[p].append(s.deck.pop(0))
        s.hands[p].sort()
        self._advance(s)

    def _advance(self, s: MutinyState) -> None:
        s.current = (s.current + 1) % self.n_players

    def _end_round(self, s: MutinyState, rng: Random) -> None:
        for p in range(self.n_players):
            s.scores[p] -= len(s.hands[p])
        if s.rnd >= ROUNDS:
            s.final_hand_counts = [len(h) for h in s.hands]
            s.phase = GAME_OVER
            s.log += "; game over"
            return
        # next starter: lowest total score, ties walked clockwise from starter+1
        lowest = min(s.scores)
        nxt = s.starter
        for i in range(self.n_players):
            cand = (s.starter + 1 + i) % self.n_players
            if s.scores[cand] == lowest:
                nxt = cand
                break
        s.starter = nxt
        s.rnd += 1
        self._deal(s, rng)

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: MutinyState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(card_str(c) for c in s.hands[p]),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "wake_top": card_str(s.wake[-1]) if s.wake else None,
            "wake_height": len(s.wake),
            "deck": len(s.deck),
            "heading": s.heading,
            "cargo": s.cargo,
            "scores": tuple(s.scores),
            "rounds_won": tuple(s.rounds_won),
            "round": s.rnd,
            "phase": s.phase,
            "current": s.current,
            "last_event": s.log,
        }

    def describe(self, s: MutinyState) -> str:
        top = card_str(s.wake[-1]) if s.wake else "-"
        return (
            f"round {s.rnd}/{ROUNDS} orders={s.heading}/{s.cargo} wake_top={top} deck={len(s.deck)} "
            f"scores={s.scores} hands={[len(h) for h in s.hands]} turn=seat {s.current} ({s.phase}); {s.log}"
        )


GAME = Mutiny
