from __future__ import annotations

from collections.abc import Hashable
from random import Random
from typing import Any, Protocol, runtime_checkable

PlayerId = int
Action = Hashable          # must be hashable + have a readable str(); tuples/strings/frozen dataclasses are fine
State = Any                # game-owned; must be deep-copyable (copy.deepcopy) for search agents
Observation = Any          # what one player may see; must be hashable-ish / json-able for logging


@runtime_checkable
class GMLike(Protocol):
    """Minimal game-master interface a game may call. See gd_gm for implementations."""

    def decide(self, prompt: str, options: list[str], context: dict[str, Any]) -> str: ...
    def narrate(self, prompt: str, context: dict[str, Any]) -> str: ...


@runtime_checkable
class Game(Protocol):
    """Pure, deterministic state machine. ALL randomness must come from the given ``rng``.

    Rules for implementers (generated games are checked against these):
    * ``setup`` returns a fresh state; never keep mutable per-game data on ``self``.
    * ``step`` must return a NEW state (or a deep copy mutated); never mutate the input.
    * ``legal_actions`` must be non-empty when not terminal.
    * ``scores`` higher is better; ties allowed; length == n_players.
    * ``observe`` hides private information of other players.
    """

    n_players: int

    def setup(self, rng: Random) -> State: ...
    def current_player(self, s: State) -> PlayerId: ...
    def legal_actions(self, s: State) -> list[Action]: ...
    def step(self, s: State, a: Action, rng: Random) -> State: ...
    def is_terminal(self, s: State) -> bool: ...
    def scores(self, s: State) -> list[float]: ...
    def observe(self, s: State, p: PlayerId) -> Observation: ...
    def describe(self, s: State) -> str: ...
