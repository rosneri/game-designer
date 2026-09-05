"""Per-idea pipeline: idea -> code -> validate -> tests -> gauntlet -> judge -> lessons."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Any

from . import llm
from .blocks import parse_file_blocks, parse_json_block, write_blocks

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

_lock = threading.Lock()
_reserved: set[str] = set()


@dataclass
class Config:
    root: Path = field(default_factory=lambda: Path.cwd())
    max_fix_rounds: int = 2
    runner_cmd: list[str] = field(default_factory=lambda: shlex.split(os.environ.get("GD_RUNNER_CMD", "uv run runner")))
    pytest_cmd: list[str] = field(default_factory=lambda: shlex.split(os.environ.get("GD_PYTEST_CMD", "uv run pytest")))
    tool_timeout: int = 600
    dry_run: bool = False

    @property
    def prompts(self) -> Path:
        return self.root / "prompts"

    @property
    def games(self) -> Path:
        return self.root / "games"


# ---------------------------------------------------------------- prompts
def render(cfg: Config, name: str, **kw: Any) -> str:
    return (cfg.prompts / f"{name}.md").read_text().format_map(kw)


def lessons_text(cfg: Config) -> str:
    p = cfg.prompts / "LESSONS.md"
    lines = [l for l in p.read_text().splitlines() if l.startswith("- ")] if p.exists() else []
    return "\n".join(lines[-40:]) or "- (none yet)"


def existing_games(games_dir: Path) -> list[dict]:
    out = []
    for sp in sorted(games_dir.glob("*/spec.json")):
        try:
            d = json.loads(sp.read_text())
            out.append({"slug": sp.parent.name, "name": d.get("name", ""), "mechanics": d.get("mechanics", [])})
        except (OSError, json.JSONDecodeError):
            out.append({"slug": sp.parent.name, "name": "", "mechanics": []})
    return out


def existing_text(games_dir: Path) -> str:
    rows = [f"- {g['slug']}: {g['name']} [{', '.join(g['mechanics'])}]" for g in existing_games(games_dir)]
    return "\n".join(rows) or "- (none)"


def gamecore_src(cfg: Config, name: str) -> str:
    return (cfg.root / "libs/gamecore/src/gd_gamecore" / name).read_text()


def example_text(cfg: Config) -> str:
    ref = cfg.games / "reference-war-plus"
    if not (ref / "rules.py").exists():
        return ""
    parts = ["## Example package (games/reference-war-plus)"]
    for f in ("spec.json", "rules.py"):
        if (ref / f).exists():
            lang = "json" if f.endswith("json") else "python"
            parts.append(f"```{lang} path=games/reference-war-plus/{f}\n{(ref / f).read_text()}\n```")
    return "\n".join(parts)


def idea_prompt(cfg: Config, seed: int) -> str:
    direction = Random(seed).choice(DIRECTIONS)
    return render(cfg, "idea", direction=direction, existing=existing_text(cfg.games), lessons=lessons_text(cfg))


def code_prompt(cfg: Config, idea: str, slug: str) -> str:
    return render(cfg, "code", contract=(cfg.prompts / "contract.md").read_text(), game_py=gamecore_src(cfg, "game.py"),
                  spec_py=gamecore_src(cfg, "spec.py"), example=example_text(cfg), idea=idea, slug=slug)


def files_text(gdir: Path, names=("spec.json", "rules.py", "test_rules.py")) -> str:
    parts = []
    for n in names:
        p = gdir / n
        if p.exists():
            lang = "json" if n.endswith("json") else "python"
            parts.append(f"```{lang} path=games/{gdir.name}/{n}\n{p.read_text()}\n```")
    return "\n".join(parts)


def fix_prompt(cfg: Config, slug: str, stage: str, error: str, extra: str = "") -> str:
    return render(cfg, "fix", contract=(cfg.prompts / "contract.md").read_text(), slug=slug, stage=stage,
                  error=error[-12000:], files=files_text(cfg.games / slug), extra=extra)


# ---------------------------------------------------------------- idea parsing
_KV = re.compile(r"^(slug|players|jokers|dice|mechanics|hidden_information|turn_order):\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def parse_idea(text: str) -> dict:
    d: dict[str, Any] = {"name": "", "slug": "", "players": (2, 4), "jokers": 0, "dice": 0, "mechanics": []}
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        d["name"] = m.group(1).strip()
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
    if not d["slug"]:
        d["slug"] = slugify(d["name"]) or "untitled"
    return d


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        return ""
    if not s[0].isalpha():
        s = "g-" + s
    return s[:40].rstrip("-") if len(s) >= 3 else s + "-game"


def reset_reservations() -> None:
    with _lock:
        _reserved.clear()


def reserve_slug(slug: str, games_dir: Path) -> str:
    """Pick a slug unused on disk and by concurrent workers (append -2, -3, ...)."""
    with _lock:
        cand, i = slug, 1
        while (games_dir / cand).exists() or cand in _reserved:
            i += 1
            cand = f"{slug[:37]}-{i}"
        _reserved.add(cand)
        return cand


# ---------------------------------------------------------------- tools
@dataclass
class ToolResult:
    ok: bool
    output: str
    seconds: float
    data: dict | None = None


def run_tool(argv: list[str], cwd: Path, timeout: int) -> ToolResult:
    t0 = time.monotonic()
    try:
        cp = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout)
        out = (cp.stdout + ("\n" + cp.stderr if cp.stderr else "")).strip()
        return ToolResult(cp.returncode == 0, out, time.monotonic() - t0)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"TIMEOUT after {timeout}s: {' '.join(argv)}", time.monotonic() - t0)
    except FileNotFoundError as e:
        return ToolResult(False, f"tool not found: {e}", time.monotonic() - t0)


def gauntlet_summary(data: dict | None, output: str) -> str:
    """Compact text of failing stages from a gauntlet JSON (schema tolerant)."""
    if not data:
        return output[-6000:]
    stages = data.get("stages", data)
    lines = []
    items = stages.items() if isinstance(stages, dict) else enumerate(stages)
    for k, v in items:
        if isinstance(v, dict) and v.get("passed", v.get("ok", True)) is False:
            lines.append(f"{v.get('name', k)}: FAIL reason={v.get('reason', v.get('error', ''))} "
                         f"metrics={json.dumps(v.get('metrics', {k2: v2 for k2, v2 in v.items() if k2 not in ('passed', 'ok', 'reason', 'name')}), default=str)}")
    return "\n".join(lines) or output[-6000:]


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


# ---------------------------------------------------------------- lessons
def append_lessons(cfg: Config, lines: list[str]) -> int:
    p = cfg.prompts / "LESSONS.md"
    with _lock:
        existing = set(p.read_text().splitlines()) if p.exists() else set()
        new = [l for l in dict.fromkeys(f"- {l.strip().lstrip('- ')}" for l in lines if l.strip()) if l not in existing]
        if new:
            with p.open("a") as f:
                f.write("\n".join(new) + "\n")
    return len(new)


def lessons_from(result: dict) -> list[str]:
    slug = result["slug"]
    out = []
    for fx in result.get("fixes", []):
        if llm.is_infra_error(fx["error"]):
            continue
        cls = fx["error"].strip().splitlines()[-1][:120] if fx["error"].strip() else "unknown"
        out.append(f"[{fx['stage']}] {slug}: failed with `{cls}`; fix {'worked' if fx['fixed'] else 'FAILED'}: {fx['change']}")
    if result.get("failed_stage"):
        if result.get("infra") or llm.is_infra_error(result.get("error", "")):
            return out  # plumbing failed; nothing to learn about game design
        out.append(f"[{result['failed_stage']}] {slug}: unrecovered after {result['fix_rounds']} fixes: {result.get('error', '')[-120:]}")
    elif result.get("judge"):
        j = result["judge"]
        dims = {k: j.get(k) for k in ("fun", "clarity", "originality", "depth", "component_fit") if isinstance(j.get(k), (int, float))}
        if dims:
            weakest = min(dims, key=dims.get)
            out.append(f"[passed] {slug}: weakest={weakest} ({dims[weakest]}/10); verdict={j.get('verdict', '?')}; note: {(j.get('notes') or [''])[0][:140]}")
    return out


# ---------------------------------------------------------------- pipeline
class Run:
    def __init__(self, run_dir: Path, idx: int, seed: int, cfg: Config):
        self.cfg, self.idx, self.seed = cfg, idx, seed
        self.run_dir = Path(run_dir)
        self.out = self.run_dir / f"idea{idx:02d}"  # renamed to slug after IDEA
        self.out.mkdir(parents=True, exist_ok=True)
        self.res: dict[str, Any] = {"idx": idx, "seed": seed, "slug": None, "passed": [], "failed_stage": None,
                                    "fix_rounds": 0, "fixes": [], "judge": None, "timings": {}, "costs": "unknown"}

    def save(self, name: str, text: str) -> None:
        (self.out / name).write_text(text)

    def ask(self, step: str, prompt: str, name: str, **kw: Any) -> llm.LLMResult:
        self.save(f"{name}.prompt.md", prompt)
        r = llm.call(prompt, step, **kw)
        self.save(f"{name}.out.txt", r.text + (f"\n\n--- stderr ---\n{r.stderr}" if r.stderr else ""))
        self.res["timings"][name] = round(r.seconds, 1)
        return r

    def fail(self, stage: str, err: str) -> dict:
        self.res.update(failed_stage=stage, error=err[-4000:], infra=llm.is_infra_error(err))
        return self.res

    def finish(self) -> dict:
        self.res["fix_rounds"] = len(self.res["fixes"])
        try:
            append_lessons(self.cfg, lessons_from(self.res))
        except OSError:
            pass
        (self.out / "result.json").write_text(json.dumps(self.res, indent=2, default=str))
        return self.res

    # -- steps
    def step_idea(self) -> dict | None:
        r = self.ask("idea", idea_prompt(self.cfg, self.seed), "idea")
        if not r.ok:
            self.fail("idea", r.stderr or "empty answer")
            return None
        info = parse_idea(r.text)
        slug = reserve_slug(info["slug"], self.cfg.games)
        info["slug"] = slug
        self.res.update(slug=slug, name=info["name"], idea=info)
        new_out = self.run_dir / slug
        if not new_out.exists():
            self.out.rename(new_out)
            self.out = new_out
        self.save("idea.md", r.text)
        self.res["passed"].append("idea")
        return info

    def write_answer(self, text: str, slug: str) -> list[Path]:
        return write_blocks(parse_file_blocks(text), self.cfg.root, f"games/{slug}/")

    def step_code(self, idea: str, slug: str) -> bool:
        prompt = code_prompt(self.cfg, idea, slug)
        r = self.ask("code", prompt, "code", cwd=str(self.cfg.root), tools=True,
                     system_append=(self.cfg.prompts / "contract.md").read_text())
        written = self.write_answer(r.text, slug) if r.text else []
        gdir = self.cfg.games / slug
        if not (gdir / "rules.py").exists() or not (gdir / "spec.json").exists():
            self.fail("code", f"missing files; written={[p.name for p in written]}; stderr={r.stderr[-500:]}")
            return False
        self.res["passed"].append("code")
        return True

    def fix_round(self, slug: str, stage: str, error: str, check, extra: str = "", budget: int | None = None) -> bool:
        """Ask opus to fix until ``check()`` passes; returns True if fixed."""
        budget = self.cfg.max_fix_rounds if budget is None else budget
        for _ in range(budget):
            n = len(self.res["fixes"]) + 1
            r = self.ask("fix", fix_prompt(self.cfg, slug, stage, error, extra), f"fix{n}", cwd=str(self.cfg.root),
                         tools=True, system_append=(self.cfg.prompts / "contract.md").read_text())
            written = self.write_answer(r.text, slug) if r.text else []
            ok, error2 = check()
            self.res["fixes"].append({"stage": stage, "error": error[-600:], "fixed": ok,
                                      "change": ", ".join(p.name for p in written) or "no files returned"})
            if ok:
                return True
            error = error2
        self.res["last_error"] = error[-4000:]
        return False

    def validate(self, slug: str) -> tuple[bool, str]:
        t = run_tool(self.cfg.runner_cmd + ["validate", f"games/{slug}"], self.cfg.root, self.cfg.tool_timeout)
        return t.ok, t.output

    def pytest(self, slug: str) -> tuple[bool, str]:
        t = run_tool(self.cfg.pytest_cmd + [f"games/{slug}", "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
                     self.cfg.root, self.cfg.tool_timeout)
        return t.ok, t.output

    def gauntlet(self, slug: str) -> tuple[bool, str]:
        jp = self.out / "gauntlet.json"
        t = run_tool(self.cfg.runner_cmd + ["gauntlet", f"games/{slug}", "--json", str(jp)], self.cfg.root,
                     self.cfg.tool_timeout)
        data = None
        if jp.exists():
            try:
                data = json.loads(jp.read_text())
            except json.JSONDecodeError:
                data = None
        self.res["gauntlet"] = data
        ok = t.ok and (data is None or data.get("passed", True) is not False)
        return ok, gauntlet_summary(data, t.output)

    def step_tests(self, slug: str, players: tuple[int, int]) -> bool:
        gdir = self.cfg.games / slug
        prompt = render(self.cfg, "tests", slug=slug, players=", ".join(map(str, range(players[0], players[1] + 1))),
                        docstring=rules_docstring(gdir), rules=(gdir / "rules.py").read_text())
        r = self.ask("tests", prompt, "tests")
        if r.text:
            self.write_answer(r.text, slug)
        if not (gdir / "test_rules.py").exists():
            self.fail("tests", f"no test file returned; stderr={r.stderr[-500:]}")
            return False
        ok, err = self.pytest(slug)
        if not ok:
            ok = self.fix_round(slug, "tests", err, lambda: self.pytest(slug), budget=1,
                                extra="The tests were auto-generated and MAY be wrong; fix rules.py or test_rules.py, whichever is at fault.")
        if not ok:
            self.fail("tests", self.res.get("last_error", err))
            return False
        self.res["passed"].append("tests")
        return True

    def step_judge(self, slug: str, idea: str) -> None:
        gdir = self.cfg.games / slug
        metrics = json.dumps(self.res.get("gauntlet") or {}, indent=1, default=str)[:8000]
        r = self.ask("judge", render(self.cfg, "judge", idea=idea[:8000], docstring=rules_docstring(gdir), metrics=metrics), "judge")
        j = parse_json_block(r.text) if r.text else None
        if j is None:
            self.fail("judge", "no JSON verdict")
            return
        j["total"] = sum(v for k, v in j.items() if k in ("fun", "clarity", "originality", "depth", "component_fit") and isinstance(v, (int, float)))
        self.res["judge"] = j
        (self.out / "judge.json").write_text(json.dumps(j, indent=2))
        self.res["passed"].append("judge")

    def run(self) -> dict:
        t0 = time.monotonic()
        try:
            self._run()
        except Exception as e:  # noqa: BLE001 - never kill the pool
            self.res.update(failed_stage=self.res.get("failed_stage") or "crash", error=f"{type(e).__name__}: {e}")
        self.res["timings"]["total"] = round(time.monotonic() - t0, 1)
        return self.finish()

    def _run(self) -> dict:
        info = self.step_idea()
        if info is None:
            return self.res
        slug, idea = info["slug"], (self.out / "idea.md").read_text()
        if not self.step_code(idea, slug):
            return self.res
        ok, err = self.validate(slug)
        if not ok and not self.fix_round(slug, "validate", err, lambda: self.validate(slug)):
            return self.fail("validate", self.res.get("last_error", err))
        self.res["passed"].append("validate")
        if not self.step_tests(slug, info["players"]):
            return self.res
        ok, err = self.gauntlet(slug)
        if not ok and not self.fix_round(slug, "gauntlet", err, lambda: self.gauntlet(slug),
                                         extra="Failing gauntlet stages with metrics are listed above. Adjust rules to fix balance/length/decision density while keeping the game's identity."):
            return self.fail("gauntlet", self.res.get("last_error", err))
        self.res["passed"].append("gauntlet")
        self.step_judge(slug, idea)
        return self.res


def run_one(run_dir: str | Path, idx: int, seed: int, cfg: Config) -> dict:
    """Run the full pipeline for one idea; returns the result dict (also saved as result.json)."""
    return Run(Path(run_dir), idx, seed, cfg).run()
