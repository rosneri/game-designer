from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Components(BaseModel):
    jokers: int = Field(0, ge=0, le=2)
    dice: int = Field(0, ge=0, le=2, description="number of d6")
    uses_full_deck: bool = True
    extra: list[str] = Field(default_factory=list, description="tokens/pen-and-paper etc.; keep empty if possible")


class GMRole(BaseModel):
    """Optional AI game master. If present, the runtime injects a GM into setup()."""

    enabled: bool = False
    role: str = ""
    decisions: list[str] = Field(default_factory=list, description="what the GM decides (used for ScriptedGM fallback)")


class GameSpec(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,40}$")
    name: str
    tagline: str = ""
    players_min: int = Field(2, ge=2, le=4)
    players_max: int = Field(4, ge=2, le=4)
    components: Components = Field(default_factory=Components)
    mechanics: list[str] = Field(default_factory=list, description="tags: trick-taking, shedding, bidding, push-your-luck, set-collection, ...")
    core_loop: str = ""
    win_condition: str = ""
    est_minutes: tuple[int, int] = (10, 30)
    gm: GMRole = Field(default_factory=GMRole)
    hidden_information: bool = True
    turn_order: Literal["clockwise", "simultaneous", "variable"] = "clockwise"

    @model_validator(mode="after")
    def _check(self) -> GameSpec:
        if self.players_min > self.players_max:
            raise ValueError("players_min > players_max")
        lo, hi = self.est_minutes
        if lo > hi or lo < 1:
            raise ValueError("bad est_minutes")
        return self

    @property
    def player_counts(self) -> range:
        return range(self.players_min, self.players_max + 1)


def load_spec(path: str | Path) -> GameSpec:
    p = Path(path)
    if p.is_dir():
        p = p / "spec.json"
    return GameSpec.model_validate(json.loads(p.read_text()))
