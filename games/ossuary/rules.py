"""placeholder"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Deck, Suit
from gd_gamecore import GMLike

N_NICHES = 5
HAND = 3
ROUNDS = {2: 18, 3: 12, 4: 9}
TRIBUTE_DIV = 1          # tribute = ceil(value / TRIBUTE_DIV)
TITHE_EVERY = 1          # rounds between tithes
BELL_DIV = 3             # last-bell payout = ceil(value / BELL_DIV)
SUIT_LETTER = {Suit.CLUBS: "C", Suit.DIAMONDS: "D", Suit.HEARTS: "H", Suit.SPADES: "S"}
RANK_VALUE = {"A": 1, "J": 11, "Q": 12, "K": 13}


def code(card) -> str:
    return f"{card.rank_name}{SUIT_LETTER[Suit(card.suit)]}"


def value(c: str) -> int:
    return RANK_VALUE.get(c[:-1], 0) or int(c[:-1])


def tribute(c: str) -> int:
    return -(-value(c) // TRIBUTE_DIV)


def rank_of(c: str) -> str:
    return c[:-1]


def suit_of(c: str) -> str:
    return c[-1]


@dataclass
class OssuaryState:
    hands: list[list[str]]
    niches: list[list[str]]
    draw: list[str]
    ash: list[str]
    trophies: list[list[str]]
    points: list[int]
    known: dict[str, set[int]]
    owner: dict[str, int]
    start: int
    turn: int
    total_turns: int
    last: tuple = ()
    log: list[str] = field(default_factory=list)


class Ossuary:
    """See the module docstring."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    def setup(self, rng: Random) -> OssuaryState:
        deck = Deck(jokers=0).shuffle(rng)
        cards = [code(c) for c in deck.cards]
        hands = [[] for _ in range(self.n_players)]
        for _ in range(HAND):
            for h in hands:
                h.append(cards.pop())
        niches = [[cards.pop()] for _ in range(N_NICHES)]
        return OssuaryState(
            hands=[sorted(h) for h in hands],
            niches=niches,
            draw=cards,
            ash=[],
            trophies=[[] for _ in range(self.n_players)],
            points=[0] * self.n_players,
            known={n[0]: set() for n in niches},
            owner={},
            start=rng.randrange(self.n_players),
            turn=0,
            total_turns=ROUNDS[self.n_players] * self.n_players,
        )

    def current_player(self, s: OssuaryState) -> int:
        return (s.start + s.turn) % self.n_players

    def is_terminal(self, s: OssuaryState) -> bool:
        return s.turn >= s.total_turns

    def legal_actions(self, s: OssuaryState) -> list[tuple]:
        p = self.current_player(s)
        hand = s.hands[p]
        acts: list[tuple] = []
        for i, niche in enumerate(s.niches):
            if niche:
                acts += [("unlock", i + 1, c) for c in hand]
        acts += [("bury", i + 1, c) for i in range(N_NICHES) for c in hand]
        acts += [("peek", i + 1) for i, niche in enumerate(s.niches) if niche]
        return acts or [("pass",)]

    def step(self, state: OssuaryState, a: tuple, rng: Random) -> OssuaryState:
        s = copy.deepcopy(state)
        p = self.current_player(s)
        kind = a[0]
        if kind == "unlock":
            i, key = a[1] - 1, a[2]
            self._check(s, p, i, key, need_relic=True)
            self._unlock(s, p, i, key)
            self._draw(s, p)
            if not s.niches[i] and s.draw:
                fresh = s.draw.pop()
                s.niches[i] = [fresh]
                s.known[fresh] = set()
        elif kind == "bury":
            i, card = a[1] - 1, a[2]
            self._check(s, p, i, card, need_relic=False)
            s.hands[p].remove(card)
            s.niches[i].append(card)
            s.known[card] = {p}
            s.owner[card] = p
            s.last = ("bury", p, i + 1)
            s.log.append(f"seat {p} buried a card on niche {i + 1}")
            self._draw(s, p)
        elif kind == "peek":
            i = a[1] - 1
            if not (0 <= i < N_NICHES) or not s.niches[i]:
                raise ValueError(f"niche {i + 1} is empty")
            s.known[s.niches[i][-1]].add(p)
            s.last = ("peek", p, i + 1)
            s.log.append(f"seat {p} peeked at niche {i + 1}")
        elif kind == "pass":
            if s.hands[p] or any(s.niches):
                raise ValueError("pass needs an empty hand and empty niches")
            s.last = ("pass", p)
        else:
            raise ValueError(f"unknown action {a!r}")
        s.turn += 1
        if s.turn % (self.n_players * TITHE_EVERY) == 0 and s.turn < s.total_turns:
            self._tithe(s)
        if s.turn == s.total_turns:
            self._last_bell(s)
        del s.log[:-6]
        return s

    def _check(self, s, p, i, card, need_relic):
        if not 0 <= i < N_NICHES:
            raise ValueError(f"no niche {i + 1}")
        if need_relic and not s.niches[i]:
            raise ValueError(f"niche {i + 1} is empty")
        if card not in s.hands[p]:
            raise ValueError(f"{card} is not in the hand of seat {p}")

    def _claim(self, s, p, i, relic, bonus):
        """Take the top of niche i. ``bonus`` is the key bonus (rank match only)."""
        s.niches[i].pop()
        s.known.pop(relic, None)
        owner = s.owner.pop(relic, None)
        s.trophies[p].append(relic)
        if owner is not None and owner != p:  # someone else's bait: the value is theirs
            s.points[owner] += value(relic)
            s.points[p] += bonus
            s.log.append(f"seat {owner} claimed {value(relic)} tribute for the relic they had buried")
        else:
            s.points[p] += value(relic) + bonus

    def _unlock(self, s, p, i, key):
        relic = s.niches[i][-1]
        s.hands[p].remove(key)
        if rank_of(relic) == rank_of(key):
            s.last = ("rank", p, i + 1, relic, key)
            s.log.append(f"seat {p} rank-matched {key} on niche {i + 1}: took {relic} (+{value(relic) + value(key)})")
            s.trophies[p].append(key)
            self._claim(s, p, i, relic, value(key))
        elif suit_of(relic) == suit_of(key):
            s.last = ("suit", p, i + 1, relic, key)
            s.log.append(f"seat {p} suit-matched {key} on niche {i + 1}: took {relic} (+{value(relic)})")
            s.ash.append(key)
            self._claim(s, p, i, relic, 0)
        else:
            s.ash.append(key)
            s.known[relic] = set(range(self.n_players))
            s.last = ("miss", p, i + 1, relic, key)
            s.log.append(f"seat {p} missed with {key} on niche {i + 1}; it holds {relic}")

    def _draw(self, s, p):
        if s.draw:
            s.hands[p].append(s.draw.pop())
            s.hands[p].sort()

    def _tithe(self, s):
        best = max(s.points)
        leaders = [p for p in range(self.n_players) if s.points[p] == best]
        if len(leaders) != 1:
            return
        p = leaders[0]
        if not s.trophies[p]:
            return
        relic = max(s.trophies[p], key=lambda c: (value(c), c))
        s.trophies[p].remove(relic)
        s.points[p] -= value(relic)
        i = min(range(N_NICHES), key=lambda k: (len(s.niches[k]), k))
        s.niches[i].append(relic)
        s.known[relic] = {p}
        s.owner.pop(relic, None)  # the ossuary owns it again: free loot for anyone
        s.last = ("tithe", p, i + 1, value(relic))
        s.log.append(f"tithe: seat {p} returned a relic worth {value(relic)} to niche {i + 1}")

    def _last_bell(self, s):
        """Final scoring: the top card of each niche pays its burier (ossuary cards pay nobody)."""
        for i, niche in enumerate(s.niches):
            if not niche:
                continue
            top = niche[-1]
            owner = s.owner.get(top)
            if owner is not None:
                s.points[owner] += -(-value(top) // BELL_DIV)
                s.known[top] = set(range(self.n_players))
                s.log.append(f"last bell: seat {owner} kept {top} on top of niche {i + 1} (+{-(-value(top) // BELL_DIV)})")

    def _tiebreak_key(self, s, p):
        vals = sorted((value(c) for c in s.trophies[p]), reverse=True)
        return (s.points[p], len(vals), tuple(vals), (p - s.start) % self.n_players)

    def scores(self, s):
        base = [float(x) for x in s.points]
        if not self.is_terminal(s):
            return base
        order = sorted(range(self.n_players), key=lambda p: self._tiebreak_key(s, p))
        for rank, p in enumerate(order):
            base[p] += rank * 1e-3
        return base

    def _visible(self, s, p, i):
        return tuple(c if p in s.known.get(c, ()) else "?" for c in s.niches[i])

    def observe(self, s, p):
        return {
            "seat": p,
            "hand": tuple(s.hands[p]),
            "niches": tuple(self._visible(s, p, i) for i in range(N_NICHES)),
            "mine_in_niches": tuple(sum(1 for c in n if s.owner.get(c) == p) for n in s.niches),
            "ash": tuple(s.ash),
            "my_trophies": tuple(sorted(s.trophies[p])),
            "trophy_counts": tuple(len(t) for t in s.trophies),
            "points": tuple(s.points),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "draw_left": len(s.draw),
            "to_move": self.current_player(s),
            "turn": s.turn,
            "turns_left": max(0, s.total_turns - s.turn),
            "last": s.last,
            "log": tuple(s.log),
        }

    def describe(self, s):
        stacks = " ".join(f"n{i + 1}:{len(n)}" for i, n in enumerate(s.niches))
        total_rounds = s.total_turns // self.n_players
        return (
            f"round {min(s.turn // self.n_players + 1, total_rounds)}/{total_rounds} "
            f"seat {self.current_player(s)} to move; points={list(s.points)}; niches [{stacks}]; "
            f"hands={[len(h) for h in s.hands]}; draw={len(s.draw)}; ash={len(s.ash)}"
        )


GAME = Ossuary
