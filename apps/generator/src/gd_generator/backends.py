"""LLM backends: fresh-context CLI calls, one subprocess per request, no SDKs.

``LLMClient`` routes a pipeline step to a backend per ``GeneratorConfig.steps`` and retries infra errors.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Protocol

from .config import GeneratorConfig, StepRoute

# Failures of the plumbing (auth, billing, rate limits, timeouts, missing binary) rather than of the answer.
# They are retried and never turned into design lessons.
INFRA_PATTERNS = ("Provider rejected the request", "credit balance", "rate limit", "rate_limit", "overloaded",
                  "TIMEOUT after", "not found:", "does not support this model", "authentication", "ECONNRESET",
                  "fetch failed", "529", "503")
NO_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "Task", "WebFetch", "WebSearch"]


def is_infra_error(text: str) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in INFRA_PATTERNS)


def is_retryable(text: str) -> bool:
    """Infra errors worth another attempt. A timeout is not: the same prompt would burn the same wall clock."""
    return is_infra_error(text) and "timeout after" not in (text or "").lower()


@dataclass
class LLMRequest:
    prompt: str
    model: str
    thinking: str = "medium"
    cwd: str | None = None
    tools: bool = False
    system_append: str | None = None
    timeout: int = 600


@dataclass
class LLMResult:
    text: str
    stderr: str = ""
    returncode: int = 0
    seconds: float = 0.0
    argv: list[str] = field(default_factory=list)
    retries: int = 0
    backend: str = ""
    model: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.text.strip())

    @property
    def infra(self) -> bool:
        return not self.ok and is_infra_error(self.stderr)

    @property
    def retryable(self) -> bool:
        return not self.ok and is_retryable(self.stderr)


class Backend(Protocol):
    name: str

    def argv(self, req: LLMRequest) -> list[str]: ...

    def env(self) -> dict[str, str]: ...


class PrimeAgentBackend:
    name = "prime-agent"

    def __init__(self, binary: list[str]):
        self.binary = list(binary)

    def argv(self, req: LLMRequest) -> list[str]:
        argv = [*self.binary, "-p", "--no-session", "--model", req.model, "--thinking", req.thinking]
        if req.cwd:
            argv += ["--cwd", str(req.cwd)]
        if not req.tools:
            argv.append("-nt")
        if req.system_append:
            argv += ["--append-system-prompt", req.system_append]
        return [*argv, "--", req.prompt]

    def env(self) -> dict[str, str]:
        return dict(os.environ)


class ClaudeCodeBackend:
    """Claude Code speaks a different CLI; only the text-only shape (no cwd, no tools) is supported."""

    name = "claude"

    def __init__(self, binary: list[str]):
        self.binary = list(binary)

    def argv(self, req: LLMRequest) -> list[str]:
        if req.cwd or req.tools:
            raise ValueError("claude backend supports text-only calls (no cwd, no tools)")
        argv = [*self.binary, "-p", "--model", req.model.split("/")[-1], "--effort", req.thinking]
        if req.system_append:
            argv += ["--append-system-prompt", req.system_append]
        argv += ["--disallowed-tools", *NO_TOOLS]
        return [*argv, "--", req.prompt]

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Claude Code prefers ANTHROPIC_API_KEY over the claude.ai login when both exist. The key is for the
        # runtime LLM GM only; the harness must bill the subscription.
        env.pop("ANTHROPIC_API_KEY", None)
        return env


def run_backend(backend: Backend, req: LLMRequest) -> LLMResult:
    argv = backend.argv(req)
    t0 = time.monotonic()
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=req.timeout, env=backend.env())
        out, err, rc = cp.stdout, cp.stderr, cp.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err, rc = f"TIMEOUT after {req.timeout}s", -1
    except FileNotFoundError as e:
        out, err, rc = "", f"{argv[0]} not found: {e}", -2
    return LLMResult(out, err, rc, time.monotonic() - t0, argv, backend=backend.name, model=req.model)


class LLMClient:
    """Routes steps to backends; retries infra errors; carries no state between calls."""

    def __init__(self, cfg: GeneratorConfig):
        self.cfg = cfg
        self.backends: dict[str, Backend] = {
            "prime-agent": PrimeAgentBackend(cfg.prime_agent_bin),
            "claude": ClaudeCodeBackend(cfg.claude_bin),
        }

    def route(self, step: str) -> StepRoute:
        return self.cfg.steps[step]

    def call(self, step: str, prompt: str, *, cwd: str | None = None, system_append: str | None = None,
             timeout: int | None = None) -> LLMResult:
        r = self.route(step)
        req = LLMRequest(prompt, r.model, r.thinking, cwd=cwd, tools=r.tools, system_append=system_append,
                         timeout=timeout or r.timeout)
        backend = self.backends[r.backend]
        attempt = 0
        t0 = time.monotonic()
        while True:
            res = run_backend(backend, req)
            if res.ok or not res.retryable or attempt >= self.cfg.llm_retries or res.returncode == -2:
                res.retries, res.seconds = attempt, time.monotonic() - t0
                return res
            attempt += 1
            time.sleep(min(30, 5 * attempt))
