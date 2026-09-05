"""Thin wrapper around the ``prime-agent`` and ``claude`` CLIs. Fresh context per call, no SDKs."""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field

MODELS = {
    "idea": ("anthropic/claude-fable-5-1", "medium"),
    "code": ("anthropic/claude-opus-5", "high"),
    "fix": ("anthropic/claude-opus-5", "high"),
    "tests": ("anthropic/claude-sonnet-5", "low"),
    "judge": ("anthropic/claude-sonnet-5", "low"),
}
# Fable ideas take ~2 min alone and 4+ min with several parallel workers; 240 s timed out in batch2.
TIMEOUTS = {"idea": 600, "code": 900, "fix": 900, "tests": 600, "judge": 300}

# prime-agent's OAuth path reports itself as claude-cli/2.1.75, which the API refuses to
# serve Fable 5.1 (needs 2.1.251+). Upstream declined to bump it (PrimeIntellect-ai/prime-agent#1962),
# so steps listed here shell out to the real Claude Code binary, which is current.
BACKENDS = {"idea": "claude"}
NO_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "Task", "WebFetch", "WebSearch"]


# Failures of the *plumbing* (auth, billing, rate limits, timeouts, missing binary) rather than of the
# model's answer. They are retried once and never turned into design lessons.
INFRA_PATTERNS = ("Provider rejected the request", "credit balance", "rate limit", "rate_limit", "overloaded",
                  "TIMEOUT after", "not found:", "does not support this model", "authentication", "ECONNRESET",
                  "fetch failed", "529", "503")


def is_infra_error(text: str) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in INFRA_PATTERNS)


@dataclass
class LLMResult:
    text: str
    stderr: str = ""
    returncode: int = 0
    seconds: float = 0.0
    argv: list[str] = field(default_factory=list)
    retries: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.text.strip())

    @property
    def infra(self) -> bool:
        return not self.ok and is_infra_error(self.stderr)


def build_argv(prompt: str, model: str, thinking: str, cwd: str | None = None,
               tools: bool = False, system_append: str | None = None,
               backend: str = "prime-agent") -> list[str]:
    if backend == "claude":
        return build_claude_argv(prompt, model, cwd=cwd, tools=tools, system_append=system_append, effort=thinking)
    binary = shlex.split(os.environ.get("GD_PRIME_AGENT_BIN", "prime-agent"))  # may include an interpreter
    argv = [*binary, "-p", "--no-session", "--model", model, "--thinking", thinking]
    if cwd:
        argv += ["--cwd", str(cwd)]
    if not tools:
        argv.append("-nt")
    if system_append:
        argv += ["--append-system-prompt", system_append]
    argv += ["--", prompt]
    return argv


def build_claude_argv(prompt: str, model: str, cwd: str | None = None,
                      tools: bool = False, system_append: str | None = None, effort: str = "medium") -> list[str]:
    """Claude Code speaks a different CLI; only the text-only shape the idea step needs."""
    if cwd or tools:
        raise ValueError("claude backend supports text-only calls (no cwd, no tools)")
    binary = shlex.split(os.environ.get("GD_CLAUDE_BIN", "claude"))
    argv = [*binary, "-p", "--model", model.split("/")[-1], "--effort", effort]
    if system_append:
        argv += ["--append-system-prompt", system_append]
    argv += ["--disallowed-tools", *NO_TOOLS]
    return [*argv, "--", prompt]


def _env_for(backend: str) -> dict[str, str]:
    env = dict(os.environ)
    if backend == "claude":
        # Claude Code prefers ANTHROPIC_API_KEY over the claude.ai login when both exist. The key is
        # for the runtime LLM GM only; the harness must bill the subscription.
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def call(prompt: str, step: str, *, cwd: str | None = None, tools: bool = False,
         system_append: str | None = None, timeout: int | None = None, retries: int = 1) -> LLMResult:
    """Run one fresh-context call for ``step`` (key of MODELS); retries infra errors once."""
    model, thinking = MODELS[step]
    backend = BACKENDS.get(step, "prime-agent")
    argv = build_argv(prompt, model, thinking, cwd=cwd, tools=tools, system_append=system_append, backend=backend)
    budget = timeout or TIMEOUTS[step]
    t0 = time.monotonic()
    attempt = 0
    while True:
        try:
            cp = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=budget, env=_env_for(backend))
            out, err, rc = cp.stdout, cp.stderr, cp.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = f"TIMEOUT after {budget}s"
            rc = -1
        except FileNotFoundError as e:
            out, err, rc = "", f"{argv[0]} not found: {e}", -2
        res = LLMResult(out, err, rc, time.monotonic() - t0, argv, attempt)
        if res.ok or not res.infra or attempt >= retries or rc == -2:
            return res
        attempt += 1
        time.sleep(min(30, 5 * attempt))
