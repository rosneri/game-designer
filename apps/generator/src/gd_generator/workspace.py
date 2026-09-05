"""Run-level snapshot and per-idea workspaces.

A run never reads the live catalog (``games/``) or the live ``prompts/`` after it starts: ``Snapshot.take``
freezes them under ``runs/<run>/snapshot/``. Each idea builds inside its own ``workspace/`` that mirrors the
repo layout (``games/<slug>/``), so parallel ideas and concurrent runs cannot see or clobber each other.
Survivors are copied into the catalog by ``Workspace.promote`` at the very end, atomically.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import GeneratorConfig

GAME_FILES = ("spec.json", "rules.py", "test_rules.py")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def git_sha(root: Path) -> str:
    try:
        cp = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False)
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except OSError:
        return ""


class Snapshot:
    """Frozen inputs of one run: prompts, lessons, catalog specs, the reference package, gauntlet.toml."""

    def __init__(self, dir: Path):
        self.dir = Path(dir)

    @property
    def prompts(self) -> Path:
        return self.dir / "prompts"

    @property
    def lessons_file(self) -> Path:
        return self.prompts / "LESSONS.md"

    @property
    def catalog_file(self) -> Path:
        return self.dir / "catalog.json"

    @property
    def games(self) -> Path:
        return self.dir / "games"

    @classmethod
    def take(cls, cfg: GeneratorConfig, run_dir: Path) -> Snapshot:
        snap = cls(run_dir / "snapshot")
        if snap.dir.exists():
            return snap  # resuming: keep the frozen inputs of the original run
        snap.prompts.mkdir(parents=True)
        for p in cfg.prompts_dir.glob("*.md"):
            shutil.copy2(p, snap.prompts / p.name)
        if not snap.lessons_file.exists():
            snap.lessons_file.write_text("# Lessons\n")
        snap.games.mkdir()
        catalog = []
        for sp in sorted(cfg.catalog_dir.glob("*/spec.json")):
            slug = sp.parent.name
            try:
                d = json.loads(sp.read_text())
            except (OSError, json.JSONDecodeError):
                d = {}
            catalog.append({"slug": slug, "name": d.get("name", ""), "mechanics": d.get("mechanics", []),
                            "components": d.get("components", {}), "hidden_information": d.get("hidden_information"),
                            "turn_order": d.get("turn_order")})
            (snap.games / slug).mkdir()
            shutil.copy2(sp, snap.games / slug / "spec.json")  # spec-only shadow: enough for novelty (s7)
            if slug == cfg.reference_game:
                for f in GAME_FILES:
                    if (sp.parent / f).exists():
                        shutil.copy2(sp.parent / f, snap.games / slug / f)
        snap.catalog_file.write_text(json.dumps(catalog, indent=1))
        gt = cfg.root / "gauntlet.toml"
        if gt.exists():
            shutil.copy2(gt, snap.dir / "gauntlet.toml")
        return snap

    def catalog(self) -> list[dict[str, Any]]:
        return json.loads(self.catalog_file.read_text()) if self.catalog_file.exists() else []

    def catalog_slugs(self) -> set[str]:
        return {g["slug"] for g in self.catalog()}

    def lesson_bullets(self) -> list[str]:
        return [l[2:] for l in self.lessons_file.read_text().splitlines() if l.startswith("- ")]

    def prompt_hashes(self) -> dict[str, str]:
        return {p.name: sha(p.read_text()) for p in sorted(self.prompts.glob("*.md"))}


class Workspace:
    """Per-idea build directory: ``<idea_dir>/workspace/games/<slug>/`` plus spec-only shadows of the catalog."""

    def __init__(self, idea_dir: Path):
        self.idea_dir = Path(idea_dir)
        self.root = self.idea_dir / "workspace"
        self.games = self.root / "games"

    def game_dir(self, slug: str) -> Path:
        return self.games / slug

    def create(self, snap: Snapshot) -> Workspace:
        self.games.mkdir(parents=True, exist_ok=True)
        for g in snap.games.iterdir():
            dst = self.games / g.name
            if g.is_dir() and not dst.exists():
                shutil.copytree(g, dst)
        gt = snap.dir / "gauntlet.toml"
        if gt.exists() and not (self.root / "gauntlet.toml").exists():
            shutil.copy2(gt, self.root / "gauntlet.toml")  # pins thresholds for this run
        return self

    def env(self) -> dict[str, str]:
        """Env for tool subprocesses: private bytecode cache so parallel workers never share __pycache__."""
        env = dict(os.environ)
        env["PYTHONPYCACHEPREFIX"] = str(self.idea_dir / ".pycache")
        return env

    def files_present(self, slug: str, names=("spec.json", "rules.py")) -> bool:
        return all((self.game_dir(slug) / n).exists() for n in names)

    def promote(self, slug: str, catalog_dir: Path, extra: dict[str, Path] | None = None) -> Path:
        """Copy the finished package into the catalog atomically (temp dir + rename)."""
        src = self.game_dir(slug)
        catalog_dir.mkdir(parents=True, exist_ok=True)
        dst = catalog_dir / slug
        tmp = Path(tempfile.mkdtemp(prefix=f".{slug}-", dir=catalog_dir))
        try:
            for f in GAME_FILES:
                if (src / f).exists():
                    shutil.copy2(src / f, tmp / f)
            for name, p in (extra or {}).items():
                if p.exists():
                    shutil.copy2(p, tmp / name)
            if dst.exists():
                shutil.rmtree(dst)
            os.rename(tmp, dst)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        return dst
