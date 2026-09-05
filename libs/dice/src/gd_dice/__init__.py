"""Six-sided dice pool (0..2 dice). Deterministic given a Random."""
from __future__ import annotations

from dataclasses import dataclass
from random import Random


@dataclass(frozen=True)
class Roll:
    values: tuple[int, ...]

    @property
    def total(self) -> int:
        return sum(self.values)

    @property
    def is_double(self) -> bool:
        return len(self.values) == 2 and self.values[0] == self.values[1]

    def __str__(self) -> str:
        return "[" + " ".join("⚀⚁⚂⚃⚄⚅"[v - 1] for v in self.values) + "]"


class DicePool:
    def __init__(self, count: int, sides: int = 6):
        if not 0 <= count <= 2:
            raise ValueError("dice count must be 0..2")
        if sides != 6:
            raise ValueError("only d6 is allowed")
        self.count, self.sides = count, sides

    def roll(self, rng: Random, count: int | None = None) -> Roll:
        n = self.count if count is None else count
        if n > self.count:
            raise ValueError("cannot roll more dice than the pool has")
        return Roll(tuple(rng.randint(1, self.sides) for _ in range(n)))


def roll_d6(rng: Random, n: int = 1) -> Roll:
    return DicePool(n).roll(rng)


__all__ = ["DicePool", "Roll", "roll_d6"]
