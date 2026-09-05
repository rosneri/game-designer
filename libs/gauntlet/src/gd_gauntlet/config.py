from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class GauntletConfig(BaseModel):
    """All gauntlet thresholds and sample sizes. Override any field via ``gauntlet.toml`` at repo root."""

    # s1
    smoke_seeds: int = 3
    # s2
    playable_games: int = 30
    max_turns: int = 1500
    # s3
    balance_games: int = 300
    seat_tolerance: float = 0.12
    max_draw_rate: float = 0.35
    # s4
    skill_games: int = 120
    skill_margin: float = 0.10          # greedy win rate must exceed 1/n + margin
    skill_max_winrate: float = 0.97     # ... and stay below this (luck exists)
    max_skill_dominance: float = 0.85   # mean over player counts of (rate - 1/n) / (1 - 1/n)
    greedy_samples: int = 3
    mcts_games: int = 6                 # informational only (never fails); MCTS is slow on long games
    mcts_sims: int = 20
    mcts_rollout: int = 15
    # s5
    min_mean_legal: float = 1.8
    max_forced_share: float = 0.6
    # s6
    turns_min: int = 15
    turns_max: int = 400
    minutes_per_turn: float = 0.1
    minutes_band: tuple[float, float] = (8.0, 35.0)
    # s7
    max_novelty_similarity: float = 0.9
    # misc
    seed: int = 0

    @classmethod
    def load(cls, start: Path | None = None) -> GauntletConfig:
        """Defaults, overridden by the nearest ``gauntlet.toml`` found walking up from ``start`` (or cwd)."""
        path = find_config_file(start)
        if path is None:
            return cls()
        data = tomllib.loads(path.read_text())
        return cls.model_validate(data.get("gauntlet", data))


def find_config_file(start: Path | None = None, name: str = "gauntlet.toml") -> Path | None:
    roots = [Path(start).resolve()] if start else []
    roots.append(Path.cwd().resolve())
    for root in roots:
        for d in [root, *root.parents]:
            p = d / name
            if p.is_file():
                return p
    return None
