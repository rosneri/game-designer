"""Self-improvement: let the harness patch its own code, behind gates.

The improve step gives the coding model the evidence from a finished run and write access to the harness
itself (prompts, libs, apps, thresholds) but never to generated games or run logs. The whole allow-listed tree
is snapshotted *before* the call; afterwards the configured gates (tests, lint) must pass or every touched file
is restored. Applied and reverted attempts are both recorded in the ledger, so the next cycle knows what has
already been tried.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backends import LLMClient
from .config import GeneratorConfig
from .harness import Edit, Harness
from .refine import run_digest

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", ".pytest_cache", ".ruff_cache", "runs", "games", ".pycache"}
MAX_FILE = 400_000


def allowed_files(root: Path, rels: list[str]) -> list[Path]:
    """Every file the improve step may touch, as paths relative to ``root``."""
    out: list[Path] = []
    for rel in rels:
        p = root / rel
        if p.is_file():
            out.append(Path(rel))
            continue
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*")):
            if not f.is_file() or any(part in SKIP_DIRS for part in f.parts) or f.stat().st_size > MAX_FILE:
                continue
            out.append(f.relative_to(root))
    return out


def digest(root: Path, rels: list[str]) -> dict[str, str]:
    return {str(rel): hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in allowed_files(root, rels)}


@dataclass
class GateResult:
    argv: list[str]
    ok: bool
    output: str
    seconds: float


@dataclass
class ImproveResult:
    applied: bool = False
    reverted: bool = False
    changed: list[str] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)
    answer: str = ""
    error: str = ""
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "reverted": self.reverted, "changed": self.changed, "error": self.error[-2000:],
                "seconds": round(self.seconds, 1),
                "gates": [{"cmd": " ".join(g.argv), "ok": g.ok, "seconds": round(g.seconds, 1),
                           "output": g.output[-2000:]} for g in self.gates]}


def snapshot(root: Path, rels: list[str], dest: Path) -> None:
    """Copy the allow-listed tree so any change can be undone byte for byte."""
    shutil.rmtree(dest, ignore_errors=True)
    for rel in allowed_files(root, rels):
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)


def revert(root: Path, changed: list[str], dest: Path, existed: set[str]) -> None:
    for rel in changed:
        target, src = root / rel, dest / rel
        if rel not in existed:
            target.unlink(missing_ok=True)          # the model created it; undo means remove
        elif src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


def run_gates(cfg: GeneratorConfig) -> list[GateResult]:
    out: list[GateResult] = []
    for argv in cfg.improve_gates:
        t0 = time.monotonic()
        try:
            cp = subprocess.run(list(argv), cwd=cfg.root, capture_output=True, text=True, check=False,
                                timeout=cfg.gate_timeout)
            ok, text = cp.returncode == 0, (cp.stdout + "\n" + cp.stderr).strip()
        except subprocess.TimeoutExpired:
            ok, text = False, f"TIMEOUT after {cfg.gate_timeout}s"
        except FileNotFoundError as e:
            ok, text = False, f"gate not found: {e}"
        out.append(GateResult(list(argv), ok, text, time.monotonic() - t0))
        if not ok:
            break  # once a gate fails the later ones say nothing useful
    return out


def build_prompt(cfg: GeneratorConfig, run_dir: Path, harness: Harness, instructions: str = "") -> str:
    history = [{"event": r.event_id, "run": r.run, "edits": [e.id for e in r.edits]}
               for r in harness.load().refinements[-5:]]
    return (cfg.prompts_dir / "improve.md").read_text().format(
        run=run_dir.name, root=cfg.root, digest=json.dumps(run_digest(run_dir), indent=1, default=str)[:20000],
        paths="\n".join(f"- {p}" for p in cfg.improve_paths), harness=harness.summary(),
        history=json.dumps(history, indent=1)[:3000],
        gates="\n".join(" ".join(g) for g in cfg.improve_gates), instructions=instructions or "(none)")


def improve(cfg: GeneratorConfig, run_dir: Path, llm: LLMClient | None = None, instructions: str = "",
            dry_run: bool = False) -> ImproveResult:
    run_dir = Path(run_dir)
    out_dir = run_dir / "improve"
    out_dir.mkdir(parents=True, exist_ok=True)
    harness = Harness(cfg.harness_file)
    res = ImproveResult()
    t0 = time.monotonic()

    prompt = build_prompt(cfg, run_dir, harness, instructions)
    (out_dir / "improve.prompt.md").write_text(prompt)
    if dry_run:
        res.answer, res.seconds = prompt, time.monotonic() - t0
        return res

    backup = out_dir / "before"
    before = digest(cfg.root, cfg.improve_paths)
    snapshot(cfg.root, cfg.improve_paths, backup)

    r = (llm or LLMClient(cfg)).call("improve", prompt, cwd=str(cfg.root))
    res.answer = r.text
    (out_dir / "improve.out.txt").write_text(r.text + (f"\n\n--- stderr ---\n{r.stderr}" if r.stderr else ""))

    after = digest(cfg.root, cfg.improve_paths)
    res.changed = sorted({k for k in set(before) | set(after) if before.get(k) != after.get(k)})
    if not res.changed:
        res.error = r.stderr or "no files changed"
        res.seconds = time.monotonic() - t0
        (out_dir / "improve.json").write_text(json.dumps(res.as_dict(), indent=2))
        return res

    res.gates = run_gates(cfg)
    res.applied = bool(res.gates) and all(g.ok for g in res.gates)
    if not res.applied:
        revert(cfg.root, res.changed, backup, set(before))
        res.reverted = True
        res.error = next((g.output for g in res.gates if not g.ok), "no gates configured")
    res.seconds = time.monotonic() - t0
    (out_dir / "improve.json").write_text(json.dumps(res.as_dict(), indent=2))
    record(harness, run_dir, res)
    return res


def record(harness: Harness, run_dir: Path, res: ImproveResult) -> None:
    """Remember the attempt in the ledger so the next cycle does not repeat a reverted idea."""
    status = "applied" if res.applied else "REVERTED (gates failed)"
    text = f"self-improvement {run_dir.name}: {status}; touched {', '.join(res.changed[:6]) or 'nothing'}"
    if res.error:
        text += f"; gate said: {res.error.strip().splitlines()[-1][:120]}"
    harness.apply([Edit(op="create", id=f"improve-{run_dir.name}", kind="memory", targets=["idea"], text=text,
                        reason="self-improvement attempt")], run=run_dir.name, trigger="auto")
