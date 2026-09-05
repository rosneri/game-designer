"""Markdown reports: a player-facing rulesheet per game, and a leaderboard across gauntlet runs."""
from __future__ import annotations

import inspect
from typing import Any

from gd_gamecore import GameSpec


def _players(spec: GameSpec) -> str:
    lo, hi = spec.players_min, spec.players_max
    return f"{lo} players" if lo == hi else f"{lo}-{hi} players"


def _components(spec: GameSpec) -> list[str]:
    c = spec.components
    out = ["Standard 52-card deck" if c.uses_full_deck else "Part of a standard 52-card deck"]
    if c.jokers:
        out[0] += f" + {c.jokers} joker{'s' if c.jokers > 1 else ''}"
    if c.dice:
        out.append(f"{c.dice} six-sided {'die' if c.dice == 1 else 'dice'}")
    out += c.extra
    return out


def rulesheet_md(spec: GameSpec, rules_docstring: str = "") -> str:
    """Render a printable rulesheet from the spec plus the rules module docstring (the full rules text)."""
    lo, hi = spec.est_minutes
    lines = [f"# {spec.name}"]
    if spec.tagline:
        lines += ["", f"*{spec.tagline}*"]
    lines += ["", f"**{_players(spec)} · {lo}-{hi} minutes**", "", "## Components"]
    lines += [f"- {x}" for x in _components(spec)]
    if spec.gm.enabled:
        lines += ["", "## Game master", "", spec.gm.role or "This game uses an AI game master."]
        if spec.gm.decisions:
            lines += ["", "The game master decides:"] + [f"- {d}" for d in spec.gm.decisions]
    if spec.core_loop:
        lines += ["", "## How a turn works", "", spec.core_loop]
    if spec.win_condition:
        lines += ["", "## Winning", "", spec.win_condition]
    body = inspect.cleandoc(rules_docstring or "")
    if body:
        lines += ["", "## Full rules", "", body]
    facts = [f"Turn order: {spec.turn_order}", "Hidden information: " + ("yes" if spec.hidden_information else "no")]
    if spec.mechanics:
        facts.append("Mechanics: " + ", ".join(spec.mechanics))
    lines += ["", "---", ""] + [f"- {f}" for f in facts]
    return "\n".join(lines) + "\n"


def _stage_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return {s["name"]: s.get("metrics", {}) for s in result.get("stages", [])}


def _first_count(m: dict[str, Any], key: str) -> str:
    """Compact 'p2/p3/p4' style list of one per-player-count metric."""
    vals = [v[key] for k, v in sorted(m.items()) if k.startswith("p") and isinstance(v, dict) and key in v]
    return "/".join("-" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v) for v in vals) or "-"


def _judge_score(result: dict[str, Any]) -> float | None:
    j = result.get("judge")
    score = result.get("judge_score")
    if score is None and isinstance(j, dict):
        score = j.get("score", j.get("total"))
    elif score is None and isinstance(j, (int, float)):
        score = j
    return None if score is None else float(score)


def _cell(x: Any) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def leaderboard_md(results: list[dict[str, Any]]) -> str:
    """Table over gauntlet results. Each dict is ``GauntletResult.to_dict()`` plus optional
    ``slug``, ``name``, ``judge`` (dict with ``score``) or ``judge_score`` keys."""
    head = ["slug", "name", "passed", "failed_stage", "stages", "turns (mean)", "greedy win",
            "draw rate", "legal/turn", "judge"]
    rows = []
    def order(r: dict[str, Any]) -> tuple:
        j = _judge_score(r)
        return (not r.get("passed"), -1.0 if j is None else -j, str(r.get("slug", "")))

    for r in sorted(results, key=order):
        j = _judge_score(r)
        m = _stage_metrics(r)
        stages = r.get("stages", [])
        rows.append([
            r.get("slug") or r.get("game_dir", "?").rstrip("/").rsplit("/", 1)[-1],
            r.get("name", "-"),
            "✅" if r.get("passed") else "❌",
            r.get("failed_stage") or "-",
            f"{sum(1 for s in stages if s.get('passed'))}/{len(stages) or 8}",
            _first_count(m.get("s6_length", {}), "mean_turns"),
            _first_count(m.get("s4_skill", {}), "greedy_win_rate"),
            _first_count(m.get("s3_balance", {}), "draw_rate"),
            str(m.get("s5_decisions", {}).get("mean_legal_actions", "-")),
            "-" if j is None else f"{j:.1f}",
        ])
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(out) + "\n"


__all__ = ["leaderboard_md", "rulesheet_md"]
