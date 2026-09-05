"""Ransom — auction for a face-up Lot and a face-down Hostage.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck (no jokers, no dice).

Ranks low to high: 2,3,...,10,J(11),Q(12),K(13),A(14). Suit order for tie-breaks,
high to low: S > H > D > C. Seats are numbered 0..P-1 clockwise.

Setup
-----
Shuffle. Deal each player one face-down **Warrant** card; the owner looks at it and keeps it
secret. Its *suit* is that player's Warrant suit (two players may share a suit). Deal each
player a hand of 6 cards. Flip 2 cards face-up as the **Lot** and place 1 card face-down as the
**Hostage**. The rest is the face-down **Draw pile**. Each player has an empty face-down
**Vault**; there is a shared Discard. The round counter starts at 1.

Warden
------
In round r the Warden is seat (r-1) mod P: seat 0 in round 1, seat 1 in round 2, and so on.

Round structure
---------------
1. *Peek.* If a Hostage exists, the Warden secretly looks at it and returns it face-down.
   Nobody else sees it. (In this implementation ``observe`` shows the Hostage card only to the
   Warden of the current round.)

2. *Opening bid (simultaneous, secret).* Every player with at least one card chooses exactly
   one card from hand and places it face-down in front of them. A player with an empty hand
   makes a **Null bid** (no card, value 0). Choices are hidden until everyone has chosen; then
   all opening bids are revealed at once. (The engine collects these choices one seat at a time
   starting with the Warden, but reveals nothing until all are in: ``observe`` shows only how
   many players have already committed.)

3. *Raise (sequential).* Starting with the Warden and going clockwise, each player who made a
   non-Null opening bid **and** still holds at least one card chooses either **Stand** (do
   nothing) or **Raise** (add exactly one more card from hand face-up onto their bid). Each
   player raises at most once per round. Players with a Null bid, or with no cards left, do not
   act. Standing keeps the card for later rounds; raising spends it now.

4. *Resolution.* A bid's value is the sum of the ranks of its cards (Null = 0). Highest value
   wins. Ties are broken by the single highest card among each tied player's bid cards (rank,
   then suit S > H > D > C). If every bid is Null nobody wins, the Lot and Hostage stay in
   place, and play skips to step 5.
   The winner puts every face-up Lot card and the Hostage (if any) face-down in their Vault; the
   Hostage is never shown to anyone else. The winner's bid cards go to the Discard. Every losing
   player's bid cards are laid face-up in the middle and become the **new Lot** (the old Lot has
   been vaulted). So an overbid that falls short is a gift to whoever wins next round.

5. *Refill.* If the Draw pile is not empty and there is no Hostage in the middle, flip the top
   card face-down as the new Hostage. Then every player draws one card from the Draw pile, in
   **catch-up order**: the player with the fewest cards in hand draws first (ties broken by
   smaller Vault, then clockwise from the Warden). A player who cannot draw (pile empty) simply
   does not. So a player who spent a card on a Raise gets first call on the thinning pile, and
   the last cards of the deck do not always fall to the same seat. Then the round counter is
   incremented.

End of game
-----------
The game ends immediately after step 4 of any round in which, at that moment, the Draw pile is
empty and every player's hand is empty. Once the Draw pile is empty every player who still holds
cards must keep bidding one card per round, so hands shrink and the game always ends. Cards left
in the middle as Lot or Hostage at that moment are unscored. (A safety cap ends the game after
200 rounds; ordinary play never reaches it.)

Scoring
-------
Each player reveals Warrant and Vault. For each Vault card: if its suit matches the owner's
Warrant suit it scores its rank (2..14); otherwise it scores 2. The Warrant card itself scores
nothing. Highest total wins.

Tie-breaks (applied as a vanishing bonus below 0.01 point, so they never change the point
order): (1) more cards in the Vault; (2) owning the single highest card in any Vault (rank, then
suit); (3) higher Warrant card. All 52 cards are unique, so this always resolves.

Clarifications
--------------
* Bid cards, once placed, are never returned to hand.
* Hand sizes drift apart, because a raise spends a card while the refill is always one card.
* Lot cards are public; Vaults and Warrants are private.
* Raising with your last card is legal and leaves you with zero cards.
* Standing is never a wasted turn: the saved card is a whole extra bid later, and a shorter hand
  moves you up the refill order while the Draw pile lasts.

Strategy note: the Lot grows from the losers' wasted bids, so a fat Lot means the last auction
was hot. Only the Warden knows whether the Hostage is an Ace or a 2, and only you know which
suit doubles or triples the value of everything you vault.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_gamecore import GMLike

HAND = 6
LOT0 = 2
ROUND_CAP = 200
OFF_SUIT = 2  # points for a vaulted card that does not match your Warrant suit

BID, RAISE, DONE = "BID", "RAISE", "DONE"


def key(c: Card) -> int:
    """Total order on cards: rank first (A high), then suit S > H > D > C."""
    return c.high_value() * 4 + int(c.suit)


@dataclass
class RansomState:
    hands: list[list[Card]]
    warrant: list[Card]
    vault: list[list[Card]]
    lot: list[Card]
    hostage: Card | None
    draw: list[Card]
    discard: list[Card]
    rnd: int = 1
    phase: str = BID
    pending: list[Card | None] = field(default_factory=list)  # secret opening bid
    committed: list[bool] = field(default_factory=list)  # has this seat chosen yet?
    bids: list[list[Card]] = field(default_factory=list)  # revealed bid cards
    raise_order: list[int] = field(default_factory=list)
    raise_idx: int = 0
    last: str = ""  # public log line for the previous resolution


class Ransom:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle ---------------------------------------------------------------------
    def setup(self, rng: Random) -> RansomState:
        p = self.n_players
        deck = Deck(jokers=0).shuffle(rng)
        warrant = deck.draw(p)
        hands = deck.deal(p, HAND)
        lot = deck.draw(LOT0)
        hostage = deck.draw_one()
        s = RansomState(
            hands=[sorted(h, key=key) for h in hands],
            warrant=warrant,
            vault=[[] for _ in range(p)],
            lot=lot,
            hostage=hostage,
            draw=list(deck.cards),
            discard=[],
        )
        self._new_round(s)
        return s

    def _new_round(self, s: RansomState) -> None:
        s.phase = BID
        s.pending = [None] * self.n_players
        s.committed = [False] * self.n_players
        s.bids = [[] for _ in range(self.n_players)]
        s.raise_order = []
        s.raise_idx = 0

    def warden(self, s: RansomState) -> int:
        return (s.rnd - 1) % self.n_players

    def _order(self, s: RansomState) -> list[int]:
        w = self.warden(s)
        return [(w + i) % self.n_players for i in range(self.n_players)]

    def _draw_order(self, s: RansomState) -> list[int]:
        """Refill order: shortest hand first, then smallest Vault, then clockwise from Warden."""
        seats = self._order(s)
        return sorted(seats, key=lambda p: (len(s.hands[p]), len(s.vault[p]), seats.index(p)))

    # -- turn interface ----------------------------------------------------------------
    def current_player(self, s: RansomState) -> int:
        if s.phase == BID:
            for p in self._order(s):
                if not s.committed[p]:
                    return p
            return self.warden(s)
        if s.phase == RAISE:
            return s.raise_order[s.raise_idx]
        return self.warden(s)

    def legal_actions(self, s: RansomState) -> list[tuple]:
        if s.phase == DONE:
            return []
        p = self.current_player(s)
        hand = s.hands[p]
        if s.phase == BID:
            if not hand:
                return [("null-bid",)]
            return [("bid", str(c)) for c in hand]
        return [("stand",)] + [("raise", str(c)) for c in hand]

    def step(self, state: RansomState, a: tuple, rng: Random) -> RansomState:
        s = copy.deepcopy(state)
        if s.phase == DONE:
            raise ValueError("game over")
        p = self.current_player(s)
        kind = a[0]
        if s.phase == BID:
            if kind == "null-bid":
                if s.hands[p]:
                    raise ValueError("seat has cards; must bid one")
                s.pending[p] = None
            elif kind == "bid":
                s.pending[p] = self._take(s, p, a[1])
            else:
                raise ValueError(f"illegal action {a} in BID")
            s.committed[p] = True
            if all(s.committed):
                self._reveal(s)
        elif s.phase == RAISE:
            if kind == "raise":
                s.bids[p].append(self._take(s, p, a[1]))
            elif kind != "stand":
                raise ValueError(f"illegal action {a} in RAISE")
            s.raise_idx += 1
            if s.raise_idx >= len(s.raise_order):
                self._resolve(s, rng)
        return s

    def _take(self, s: RansomState, p: int, name: str) -> Card:
        for i, c in enumerate(s.hands[p]):
            if str(c) == name:
                return s.hands[p].pop(i)
        raise ValueError(f"{name} not in hand of seat {p}")

    def _reveal(self, s: RansomState) -> None:
        for p in range(self.n_players):
            s.bids[p] = [s.pending[p]] if s.pending[p] is not None else []
        s.raise_order = [p for p in self._order(s) if s.bids[p] and s.hands[p]]
        s.raise_idx = 0
        if s.raise_order:
            s.phase = RAISE
        else:
            self._resolve(s, None)

    # -- resolution --------------------------------------------------------------------
    def _resolve(self, s: RansomState, rng: Random | None) -> None:
        vals = [sum(c.high_value() for c in b) for b in s.bids]
        best = max(vals)
        if best == 0:  # everyone made a Null bid: no winner, middle stays put
            s.last = f"r{s.rnd}: all Null, no winner"
        else:
            tied = [p for p in range(self.n_players) if vals[p] == best]
            w = max(tied, key=lambda p: max(key(c) for c in s.bids[p]))
            taken = list(s.lot) + ([s.hostage] if s.hostage else [])
            s.vault[w].extend(taken)
            s.discard.extend(s.bids[w])
            s.hostage = None
            s.lot = [c for p in self._order(s) if p != w for c in s.bids[p]]
            s.last = f"r{s.rnd}: seat {w} won {len(taken)} card(s) with {best}"
            s.bids = [[] for _ in range(self.n_players)]
        # end check: nothing left to draw and nothing left to bid
        if not s.draw and not any(s.hands):
            s.phase = DONE
            return
        if s.draw and s.hostage is None:
            s.hostage = s.draw.pop(0)
        for p in self._draw_order(s):
            if s.draw:
                s.hands[p].append(s.draw.pop(0))
                s.hands[p].sort(key=key)
        s.rnd += 1
        if s.rnd > ROUND_CAP:  # safety terminator, never reached in normal play
            s.phase = DONE
            return
        self._new_round(s)

    def is_terminal(self, s: RansomState) -> bool:
        return s.phase == DONE

    # -- scoring -----------------------------------------------------------------------
    def _points(self, s: RansomState, p: int) -> int:
        suit = s.warrant[p].suit
        return sum(c.high_value() if c.suit == suit else OFF_SUIT for c in s.vault[p])

    def scores(self, s: RansomState) -> list[float]:
        out = []
        for p in range(self.n_players):
            top = max((key(c) for c in s.vault[p]), default=0)
            tb = 1e-4 * len(s.vault[p]) + 1e-6 * top + 1e-9 * key(s.warrant[p])
            out.append(float(self._points(s, p)) + tb)
        return out

    # -- views -------------------------------------------------------------------------
    def observe(self, s: RansomState, p: int) -> dict:
        w = self.warden(s)
        return {
            "seat": p,
            "round": s.rnd,
            "phase": s.phase,
            "warden": w,
            "you_are_warden": p == w,
            "hand": [str(c) for c in s.hands[p]],
            "warrant": str(s.warrant[p]),
            "vault": [str(c) for c in s.vault[p]],
            "your_points": self._points(s, p),
            "lot": [str(c) for c in s.lot],
            "hostage": (str(s.hostage) if (s.hostage and p == w) else ("face-down" if s.hostage else "none")),
            "draw_left": len(s.draw),
            "hand_sizes": [len(h) for h in s.hands],
            "vault_sizes": [len(v) for v in s.vault],
            # opening bids stay secret until every seat has committed
            "bids": ([[str(c) for c in b] for b in s.bids] if s.phase != BID
                     else [(["your bid"] if (q == p and s.committed[q]) else []) for q in range(self.n_players)]),
            "committed": sum(s.committed) if s.phase == BID else self.n_players,
            "to_act": None if s.phase == DONE else self.current_player(s),
            "last": s.last,
        }

    def describe(self, s: RansomState) -> str:
        lot = " ".join(str(c) for c in s.lot) or "-"
        host = "none" if s.hostage is None else "face-down"
        if s.phase == DONE:
            return f"game over after round {s.rnd}: points={[self._points(s, p) for p in range(self.n_players)]}"
        bids = " | ".join(
            ("?" if s.phase == BID and s.committed[p] else "-") if s.phase == BID
            else (" ".join(str(c) for c in s.bids[p]) or "null")
            for p in range(self.n_players)
        )
        return (
            f"round {s.rnd} [{s.phase}] warden=seat {self.warden(s)} lot=[{lot}] hostage={host} "
            f"draw={len(s.draw)} hands={[len(h) for h in s.hands]} vaults={[len(v) for v in s.vault]} bids: {bids}"
        )


GAME = Ransom
