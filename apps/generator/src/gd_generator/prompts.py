"""Prompt rendering from a frozen snapshot, idea parsing, and direction steering."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from random import Random
from typing import Any

from .models import IdeaBrief
from .workspace import Snapshot

DIRECTIONS = [
    "trick-taking with a twist on following suit", "push-your-luck drawing from a shared deck",
    "simultaneous secret bidding with cards as currency", "set collection with a rotating market row",
    "shedding race where jokers change the rules", "dice modify card values each round",
    "climbing game with ranked combinations", "bluffing about hidden card values",
    "area control on a grid of face-down cards", "auction where you pay with cards from hand",
    "memory of face-down cards with peeking actions", "cooperative-competitive: shared goal, one traitor",
    "engine building with cards as permanent upgrades", "drafting hands then scoring patterns",
    "racing along a track built from cards", "hand management with a strict card economy",
    "one die decides the trump suit each trick", "stock market of suits with rising and falling values",
    "dungeon crawl where cards are monsters and loot", "tableau building with adjacency bonuses",
    "negotiation-free trading via blind swaps", "capture game using number sums and products",
]
_STOP = {"with", "a", "the", "of", "on", "where", "from", "and", "as", "then", "via", "each", "one", "that", "you"}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in _STOP and len(w) > 2}


def choose_direction(seed: int, catalog_tags: set[str], used: set[str] = frozenset()) -> str:
    """Least-covered direction wins: fewest word overlaps with the catalog's mechanic tags; seed breaks ties.
    Directions already used in this batch are pushed to the back."""
    cat = set()
    for t in catalog_tags:
        cat |= _words(t.replace("-", " "))
    rng = Random(seed)
    scored = [((d in used), len(_words(d) & cat), rng.random(), d) for d in DIRECTIONS]
    return min(scored)[3]


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        return ""
    if not s[0].isalpha():
        s = "g-" + s
    return s[:40].rstrip("-") if len(s) >= 3 else s + "-game"


_KV = re.compile(r"^(slug|players|jokers|dice|mechanics|hidden_information|turn_order):\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def parse_idea(text: str, direction: str = "") -> IdeaBrief:
    d: dict[str, Any] = {"direction": direction}
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    d["name"] = m.group(1).strip() if m else ""
    for k, v in _KV.findall(text):
        k, v = k.lower(), v.strip().strip("`*")
        if k == "slug":
            d["slug"] = slugify(v)
        elif k == "players":
            nums = [int(x) for x in re.findall(r"\d", v)]
            if nums:
                lo, hi = max(2, min(nums)), min(4, max(nums))
                d["players"] = (lo, max(lo, hi))
        elif k in ("jokers", "dice"):
            nums = re.findall(r"\d", v)
            d[k] = max(0, min(2, int(nums[0]))) if nums else 0
        elif k == "mechanics":
            d[k] = [t.strip().lower() for t in v.split(",") if t.strip()]
        else:
            d[k] = v.lower()
    if not d.get("slug"):
        d["slug"] = slugify(d["name"]) or "untitled"
    return IdeaBrief(**d)


def bgg_tag(name: str) -> str:
    """BGG taxonomy name -> our kebab-tag convention, e.g. "Hand Management" -> "hand-management"."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


@cache
def _bgg_list(root: Path, group: str) -> tuple[dict, ...]:
    p = root / "data" / "bgg" / f"{group}.json"
    if not p.exists():
        return ()
    return tuple(json.loads(p.read_text()))


def taxonomy_menu(root: Path, mechanics_limit: int = 120, categories_limit: int = 60) -> str:
    """A compact menu of real BoardGameGeek mechanic/category/subdomain names (most-used first), so the
    idea step picks tags that exist in the taxonomy instead of inventing ad hoc ones. Empty if
    ``data/bgg/`` hasn't been populated (run ``uv run sourcing bgg categories|mechanics|families``)."""
    root = Path(root)
    mechanics = _bgg_list(root, "mechanics")[:mechanics_limit]
    categories = _bgg_list(root, "categories")[:categories_limit]
    subdomains = _bgg_list(root, "subdomains")
    if not (mechanics or categories):
        return ""
    parts = ["## BoardGameGeek taxonomy (real tags; pick from here instead of inventing new ones)"]
    if mechanics:
        parts.append("Mechanics: " + ", ".join(bgg_tag(m["name"]) for m in mechanics))
    if categories:
        parts.append("Categories: " + ", ".join(bgg_tag(c["name"]) for c in categories))
    if subdomains:
        parts.append("Subdomains: " + ", ".join(bgg_tag(s["name"]) for s in subdomains))
    parts.append("(Full lists with descriptions and BGG links live in data/bgg/*.json.)")
    return "\n".join(parts)


class Prompts:
    """Renders the frozen prompt templates of one run.

    The templates are immutable; everything learned is injected through the providers: ``lessons`` (this run's
    live board), ``harness`` (the continual-harness ledger) and ``peers`` (briefs already accepted this run).
    """

    def __init__(self, snap: Snapshot, root: Path, reference_game: str,
                 lessons: Callable[[], str] | None = None, harness: Callable[[str], str] | None = None,
                 peers: Callable[[], list[IdeaBrief]] | None = None):
        self.snap, self.root, self.reference_game = snap, Path(root), reference_game
        self._lessons, self._harness, self._peers = lessons, harness, peers

    def render(self, name: str, **kw: Any) -> str:
        return (self.snap.prompts / f"{name}.md").read_text().format_map(kw)

    def contract(self) -> str:
        return (self.snap.prompts / "contract.md").read_text()

    def lessons_text(self) -> str:
        if self._lessons:
            return self._lessons()
        lines = [l for l in self.snap.lessons_file.read_text().splitlines() if l.startswith("- ")]
        return "\n".join(lines[-40:]) or "- (none yet)"

    def harness_text(self, prompt: str) -> str:
        return self._harness(prompt) if self._harness else "- (none yet)"

    def existing_text(self, extra: list[IdeaBrief] = ()) -> str:
        rows = [f"- {g['slug']}: {g['name']} [{', '.join(g.get('mechanics', []))}]" for g in self.snap.catalog()]
        rows += [f"- {b.slug}: {b.name} [{', '.join(b.mechanics)}]" for b in extra]
        return "\n".join(rows) or "- (none)"

    def gamecore_src(self, name: str) -> str:
        return (self.root / "libs/gamecore/src/gd_gamecore" / name).read_text()

    def example_text(self) -> str:
        ref = self.snap.games / self.reference_game
        if not (ref / "rules.py").exists():
            return ""
        parts = [f"## Example package (games/{self.reference_game})"]
        for f in ("spec.json", "rules.py"):
            if (ref / f).exists():
                lang = "json" if f.endswith("json") else "python"
                parts.append(f"```{lang} path=games/{self.reference_game}/{f}\n{(ref / f).read_text()}\n```")
        return "\n".join(parts)

    def taxonomy_text(self) -> str:
        return taxonomy_menu(self.root)

    def idea(self, direction: str, extra: list[IdeaBrief] = ()) -> str:
        return self.render("idea", direction=direction, existing=self.existing_text(extra), lessons=self.lessons_text(),
                           taxonomy=self.taxonomy_text(), harness=self.harness_text("idea"))

    def tool_cmds(self, slug: str, game_dir: Path) -> dict[str, str]:
        proj = f"uv run --project {self.root}"
        game_dir = Path(game_dir).resolve()
        return {"game_dir": str(game_dir), "validate_cmd": f"{proj} runner validate {game_dir}",
                "sim_cmd": f"{proj} runner sim {game_dir} --players N --games 60 --agents greedy,random",
                "gauntlet_cmd": f"{proj} runner gauntlet {game_dir}"}

    def code(self, idea: str, slug: str, game_dir: Path) -> str:
        return self.render("code", contract=self.contract(), game_py=self.gamecore_src("game.py"),
                           spec_py=self.gamecore_src("spec.py"), example=self.example_text(), idea=idea, slug=slug,
                           harness=self.harness_text("code"), **self.tool_cmds(slug, game_dir))

    def fix(self, slug: str, game_dir: Path, stage: str, error: str, extra: str = "") -> str:
        return self.render("fix", contract=self.contract(), slug=slug, stage=stage, error=error[-12000:],
                           files=files_text(game_dir), extra=extra, harness=self.harness_text("fix"),
                           **self.tool_cmds(slug, game_dir))

    def tests(self, slug: str, players: tuple[int, int], game_dir: Path) -> str:
        return self.render("tests", slug=slug, players=", ".join(map(str, range(players[0], players[1] + 1))),
                           docstring=rules_docstring(game_dir), rules=(game_dir / "rules.py").read_text())

    def judge(self, idea: str, game_dir: Path, metrics: str) -> str:
        return self.render("judge", idea=idea[:8000], docstring=rules_docstring(game_dir), metrics=metrics)


def files_text(gdir: Path, names=("spec.json", "rules.py", "test_rules.py")) -> str:
    parts = []
    for n in names:
        p = gdir / n
        if p.exists():
            lang = "json" if n.endswith("json") else "python"
            parts.append(f"```{lang} path=games/{gdir.name}/{n}\n{p.read_text()}\n```")
    return "\n".join(parts)


def rules_docstring(gdir: Path) -> str:
    import ast
    try:
        tree = ast.parse((gdir / "rules.py").read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and ast.get_docstring(node):
                return ast.get_docstring(node) or ""
        return ast.get_docstring(tree) or ""
    except (OSError, SyntaxError):
        return ""
