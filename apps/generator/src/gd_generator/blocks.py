"""Parse fenced code blocks tagged with a path, e.g. ```python path=games/x/rules.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

_FENCE = re.compile(
    r"^```[ \t]*(?P<lang>[\w+-]*)[^\n]*?path=(?P<path>[^\s`]+)[^\n]*\n(?P<body>.*?)^```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_JSON = re.compile(r"```json[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)


def parse_file_blocks(text: str) -> dict[str, str]:
    """Return {relative_path: content}. Later blocks for the same path win."""
    out: dict[str, str] = {}
    for m in _FENCE.finditer(text):
        body = m.group("body")
        out[m.group("path").strip()] = body if body.endswith("\n") else body + "\n"
    return out


def write_blocks(blocks: dict[str, str], root: Path, allow_prefix: str) -> list[Path]:
    """Write blocks whose path starts with ``allow_prefix`` under ``root``; return written paths."""
    written = []
    for rel, body in blocks.items():
        rel = rel.lstrip("./")
        if not rel.startswith(allow_prefix) or ".." in Path(rel).parts:
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        written.append(p)
    return written


def parse_json_block(text: str) -> dict | None:
    """Find the last ```json block (or a bare JSON object) and parse it."""
    cands = [m.group(1) for m in _JSON.finditer(text)]
    if not cands:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 < j:
            cands = [text[i : j + 1]]
    for c in reversed(cands):
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None
