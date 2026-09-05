"""Generator configuration: one immutable object per run, loadable from ``generator.toml``.

Nothing in the package reads module-level constants or the environment at call time; everything a run
needs is resolved here once and copied into the run manifest for provenance.
"""
from __future__ import annotations

import os
import shlex
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

BackendName = Literal["prime-agent", "claude"]


class StepRoute(BaseModel):
    """Which backend/model answers one pipeline step."""

    backend: BackendName = "prime-agent"
    model: str
    thinking: str = "medium"
    timeout: int = 600
    tools: bool = False  # give the agent shell/file access (code/fix steps only)


# prime-agent's OAuth path reports itself as claude-cli/2.1.75, which the API refuses to serve Fable 5.1
# (needs 2.1.251+). Upstream declined to bump it (PrimeIntellect-ai/prime-agent#1962), so the idea step
# goes through the real Claude Code binary. Everything else stays on prime-agent.
DEFAULT_STEPS: dict[str, StepRoute] = {
    "idea": StepRoute(backend="claude", model="anthropic/claude-fable-5-1", thinking="medium", timeout=600),
    "code": StepRoute(model="anthropic/claude-opus-5", thinking="high", timeout=900, tools=True),
    "fix": StepRoute(model="anthropic/claude-opus-5", thinking="high", timeout=900, tools=True),
    "tests": StepRoute(model="anthropic/claude-sonnet-5", thinking="low", timeout=600),
    "judge": StepRoute(model="anthropic/claude-sonnet-5", thinking="low", timeout=300),
    # self-improvement: reflect on a finished run (fable) and patch the harness itself (opus, with tools)
    "refine": StepRoute(backend="claude", model="anthropic/claude-fable-5-1", thinking="medium", timeout=600),
    "improve": StepRoute(model="anthropic/claude-opus-5", thinking="high", timeout=1800, tools=True),
}


class GeneratorConfig(BaseModel):
    root: Path
    steps: dict[str, StepRoute] = Field(default_factory=lambda: dict(DEFAULT_STEPS))
    # binaries (argv prefixes; may include an interpreter, e.g. "python stub.py")
    prime_agent_bin: list[str] = Field(default_factory=lambda: ["prime-agent"])
    claude_bin: list[str] = Field(default_factory=lambda: ["claude"])
    runner_cmd: list[str] = Field(default_factory=lambda: ["uv", "run", "runner"])
    pytest_cmd: list[str] = Field(default_factory=lambda: ["uv", "run", "pytest"])
    # budgets
    mode: Literal["rolling", "phased"] = "rolling"
    live_lessons: bool = True        # publish each game's lessons to later ideas of the same run
    max_fix_rounds: int = 2          # validate / gauntlet repair budget
    tests_fix_rounds: int = 1        # repair budget when auto-generated tests fail
    llm_retries: int = 1             # extra attempts on infra errors (auth, billing, timeout)
    tool_timeout: int = 600
    parallel: int = 3
    # self-improvement
    improve_paths: list[str] = Field(default_factory=lambda: ["prompts", "libs", "apps", "gauntlet.toml", "generator.toml"])
    improve_gates: list[list[str]] = Field(default_factory=lambda: [["uv", "run", "pytest", "-q", "--no-header",
                                                                    "-p", "no:cacheprovider", "libs", "apps"],
                                                                   ["uv", "run", "ruff", "check", "libs", "apps"]])
    gate_timeout: int = 1800
    max_refine_edits: int = 8
    # git: commit each finished game (and each flywheel step) as it lands
    commit_each_game: bool = False
    push_commits: bool = False
    git_remote: str = "origin"
    git_branch: str = ""            # empty: whatever branch is checked out
    # batch behaviour
    dedupe_similarity: float = 0.75  # cull a brief whose mechanic tags overlap this much with an earlier one
    promote: bool = True             # copy survivors into the catalog (games/) at the end of the run
    reference_game: str = "reference-war-plus"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def catalog_dir(self) -> Path:
        return self.root / "games"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def harness_file(self) -> Path:
        """Continual-harness ledger: what the generator has learned about generating."""
        return self.prompts_dir / "harness_state.json"

    def manifest_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["root"] = str(self.root)
        return d

    @classmethod
    def load(cls, root: str | Path, path: str | Path | None = None, **overrides: Any) -> GeneratorConfig:
        """Defaults < ``<root>/generator.toml`` (or ``path``) < GD_* env vars < explicit overrides."""
        root = Path(root).resolve()
        data: dict[str, Any] = {}
        cfg_path = Path(path) if path else root / "generator.toml"
        if cfg_path.is_file():
            data = tomllib.loads(cfg_path.read_text()).get("generator", {})
        steps = dict(DEFAULT_STEPS)
        for name, spec in data.pop("steps", {}).items():
            steps[name] = StepRoute(**{**steps[name].model_dump(), **spec}) if name in steps else StepRoute(**spec)
        env = os.environ
        for key, field in (("GD_PRIME_AGENT_BIN", "prime_agent_bin"), ("GD_CLAUDE_BIN", "claude_bin"),
                           ("GD_RUNNER_CMD", "runner_cmd"), ("GD_PYTEST_CMD", "pytest_cmd")):
            if env.get(key):
                data[field] = shlex.split(env[key])
        data.update({k: v for k, v in overrides.items() if v is not None})
        return cls(root=root, steps=steps, **data)
