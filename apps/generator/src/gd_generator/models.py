"""Typed records shared by the pipeline, the report and the lessons store."""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

StepStatus = Literal["ok", "failed", "infra", "skipped"]


class IdeaBrief(BaseModel):
    name: str = ""
    slug: str = ""
    players: tuple[int, int] = (2, 4)
    jokers: int = 0
    dice: int = 0
    mechanics: list[str] = Field(default_factory=list)
    hidden_information: str = ""
    turn_order: str = ""
    direction: str = ""

    def tags(self) -> set[str]:
        return {m.strip().lower() for m in self.mechanics if m.strip()}


class StepRecord(BaseModel):
    """One executed pipeline step. Persisted as ``steps/<name>.json`` so a run can resume."""

    name: str
    status: StepStatus
    backend: str = ""
    model: str = ""
    seconds: float = 0.0
    retries: int = 0
    error: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)  # label -> path relative to the idea dir
    started: float = Field(default_factory=time.time)


class FixRecord(BaseModel):
    stage: str
    attempt: int
    error: str
    fixed: bool
    changed: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    fun: int = 0
    clarity: int = 0
    originality: int = 0
    depth: int = 0
    component_fit: int = 0
    verdict: str = "iterate"
    notes: list[str] = Field(default_factory=list)
    summary: str = ""

    @property
    def total(self) -> int:
        return self.fun + self.clarity + self.originality + self.depth + self.component_fit

    def as_dict(self) -> dict[str, Any]:
        return {**self.model_dump(), "total": self.total}


class IdeaResult(BaseModel):
    idx: int
    seed: int
    slug: str | None = None
    name: str = ""
    brief: IdeaBrief | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    fixes: list[FixRecord] = Field(default_factory=list)
    gauntlet: dict[str, Any] | None = None
    judge: JudgeVerdict | None = None
    failed_stage: str | None = None
    infra: bool = False
    error: str = ""
    promoted: bool = False
    rejected: bool = False           # passed the gauntlet but scored below min_judge_total
    timings: dict[str, float] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.failed_stage is None

    @property
    def fix_rounds(self) -> int:
        return len(self.fixes)

    def step(self, name: str) -> StepRecord | None:
        return next((s for s in self.steps if s.name == name), None)

    def summary_dict(self) -> dict[str, Any]:
        """Flat dict for results.json / reports."""
        d = self.model_dump(mode="json")
        d["passed"] = self.passed
        d["fix_rounds"] = self.fix_rounds
        d["judge"] = self.judge.as_dict() if self.judge else None
        return d


class RunManifest(BaseModel):
    run_id: str
    created: str
    n: int
    seed: int
    config: dict[str, Any]
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    lessons_hash: str = ""
    catalog: list[str] = Field(default_factory=list)
    git_sha: str = ""
    harness_entries: int = 0
