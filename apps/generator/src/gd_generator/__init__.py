"""Game-designer generator.

Per idea: idea -> code -> validate -> tests -> gauntlet -> judge -> promote, each in its own workspace, against
a frozen snapshot of prompts and catalog. Lessons publish game by game; a continual-harness ledger and a gated
self-improvement step close the loop (see ``flywheel``).
"""
from .config import GeneratorConfig
from .harness import Harness
from .improve import improve
from .models import IdeaBrief, IdeaResult, JudgeVerdict, RunManifest, StepRecord
from .pipeline import Batch
from .refine import refine

__all__ = ["Batch", "GeneratorConfig", "Harness", "IdeaBrief", "IdeaResult", "JudgeVerdict", "RunManifest",
           "StepRecord", "improve", "refine"]
