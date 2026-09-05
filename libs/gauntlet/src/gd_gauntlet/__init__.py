"""Deterministic gauntlet for game packages: ``run_gauntlet(game_dir) -> GauntletResult``.

Stages (in order): s0_schema, s1_import, s2_playable, s3_balance, s4_skill, s5_decisions,
s6_length, s7_novelty. Thresholds live in :class:`GauntletConfig` (override via ``gauntlet.toml``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import GauntletConfig, find_config_file
from .stages import STAGES, Context, StageResult, fingerprint, jaccard, run_stage


@dataclass
class GauntletResult:
    game_dir: str
    stages: list[StageResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.stages) == len(STAGES) and all(s.passed for s in self.stages)

    @property
    def failed_stage(self) -> str | None:
        return next((s.name for s in self.stages if not s.passed), None)

    @property
    def seconds(self) -> float:
        return sum(s.seconds for s in self.stages)

    def to_dict(self) -> dict[str, Any]:
        return {"game_dir": self.game_dir, "passed": self.passed, "failed_stage": self.failed_stage,
                "seconds": round(self.seconds, 2), "stages": [s.to_dict() for s in self.stages]}

    def summary(self) -> str:
        done = f"{sum(s.passed for s in self.stages)}/{len(STAGES)} stages"
        if self.passed:
            return f"PASS {Path(self.game_dir).name}: {done} in {self.seconds:.1f}s"
        bad = next(s for s in self.stages if not s.passed)
        return f"FAIL {Path(self.game_dir).name} at {bad.name}: {bad.reason} ({done}, {self.seconds:.1f}s)"


def run_gauntlet(game_dir: str | Path, config: GauntletConfig | None = None,
                 stop_on_fail: bool = True) -> GauntletResult:
    """Run all stages on ``game_dir`` (contains ``spec.json`` and ``rules.py``)."""
    game_dir = Path(game_dir)
    cfg = config or GauntletConfig.load(game_dir)
    ctx = Context(game_dir=game_dir, cfg=cfg)
    result = GauntletResult(str(game_dir))
    for fn in STAGES:
        res = run_stage(fn, ctx)
        result.stages.append(res)
        if not res.passed and stop_on_fail:
            break
        if not res.passed and fn.__name__ in ("s0_schema", "s1_import"):
            break  # later stages need spec/game; cannot continue
    return result


__all__ = [
    "STAGES",
    "GauntletConfig",
    "GauntletResult",
    "StageResult",
    "find_config_file",
    "fingerprint",
    "jaccard",
    "run_gauntlet",
]
