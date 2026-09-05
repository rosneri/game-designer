"""Game contract shared by every generated game, every agent and the gauntlet.

A game package exposes ``GAME: type[Game]`` from ``rules.py`` and a ``spec.json``
that validates as :class:`GameSpec`.
"""
from .game import Action, Game, GMLike, Observation, PlayerId, State
from .play import PlayResult, TurnRecord, load_game_module, play_game
from .spec import Components, GameSpec, GMRole, load_spec

__all__ = [
    "Action",
    "Components",
    "GMLike",
    "GMRole",
    "Game",
    "GameSpec",
    "Observation",
    "PlayResult",
    "PlayerId",
    "State",
    "TurnRecord",
    "load_game_module",
    "load_spec",
    "play_game",
]
