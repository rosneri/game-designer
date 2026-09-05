"""Committing and pushing from inside a run.

A batch commits each finished game as it lands, and the flywheel commits what `learn`, `refine` and `improve`
change. Only named paths are ever staged: the repository may have other work in flight (another agent, an open
editor), and `git add -A` would sweep it into our commit.

Every git call goes through one process-wide lock and retries when another process holds `index.lock`.
Nothing here raises into the pipeline: a failed commit or push is reported and the run continues.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_git_lock = threading.Lock()
LOCK_RETRIES = 5


@dataclass
class GitResult:
    ok: bool
    output: str = ""

    def __bool__(self) -> bool:
        return self.ok


class GitRepo:
    """Serialized, best-effort git access for a running batch."""

    def __init__(self, root: Path, remote: str = "origin", branch: str = "", push: bool = False,
                 enabled: bool = True, timeout: int = 300):
        self.root, self.remote, self.branch = Path(root), remote, branch
        self.do_push, self.enabled, self.timeout = push, enabled, timeout

    # ---------------------------------------------------------------- plumbing
    def _run(self, *args: str, retries: int = LOCK_RETRIES) -> GitResult:
        for attempt in range(retries + 1):
            try:
                cp = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True,
                                    check=False, timeout=self.timeout)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                return GitResult(False, f"{type(e).__name__}: {e}")
            out = (cp.stdout + ("\n" + cp.stderr if cp.stderr else "")).strip()
            if cp.returncode == 0:
                return GitResult(True, out)
            if "index.lock" in out and attempt < retries:
                time.sleep(1.5 * (attempt + 1))  # another process is mid-commit
                continue
            return GitResult(False, out)
        return GitResult(False, "gave up waiting for index.lock")

    def current_branch(self) -> str:
        return self.branch or self._run("rev-parse", "--abbrev-ref", "HEAD").output or "main"

    # ---------------------------------------------------------------- api
    def commit(self, paths: list[Path | str], message: str) -> GitResult:
        """Stage exactly ``paths`` and commit them. No-op when they hold nothing new."""
        if not self.enabled:
            return GitResult(True, "git disabled")
        rels = [str(p) for p in paths if (self.root / p).exists() or str(p).startswith(":")]
        if not rels:
            return GitResult(True, "nothing to commit")
        with _git_lock:
            add = self._run("add", "--", *rels)
            if not add:
                return GitResult(False, f"git add failed: {add.output}")
            if self._run("diff", "--cached", "--quiet", "--", *rels).ok:
                return GitResult(True, "nothing to commit")
            res = self._run("commit", "-m", message, "--only", "--", *rels)
            if not res:
                return GitResult(False, f"git commit failed: {res.output}")
            return GitResult(True, self._run("rev-parse", "--short", "HEAD").output)

    def push(self) -> GitResult:
        """Push, rebasing once onto the remote when someone else got there first."""
        if not (self.enabled and self.do_push):
            return GitResult(True, "push disabled")
        branch = self.current_branch()
        with _git_lock:
            res = self._run("push", self.remote, branch)
            if res:
                return res
            pull = self._run("pull", "--rebase", self.remote, branch)
            if not pull:
                return GitResult(False, f"push rejected and rebase failed: {pull.output}")
            return self._run("push", self.remote, branch)

    def commit_and_push(self, paths: list[Path | str], message: str) -> GitResult:
        res = self.commit(paths, message)
        if not res or res.output == "nothing to commit":
            return res
        pushed = self.push()
        return GitResult(True, f"{res.output}{'' if pushed else f' (push failed: {pushed.output[-200:]})'}")
