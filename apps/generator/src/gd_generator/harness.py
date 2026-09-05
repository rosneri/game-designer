"""Continual-harness state: the generator's own memory, modelled on prime-agent's ledger.

The prompt *templates* in ``prompts/*.md`` are the immutable base. Everything the harness learns about how to
generate better games lives here as supplemental entries that are rendered into the prompts at run time, and
every change is a recorded event with before/after snapshots so it can be rolled back.

Entries are addressed by id; a refinement is a bounded batch of create/update/delete edits.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

EntryKind = Literal["note", "memory", "constraint", "skill"]
# Which prompt each entry kind is rendered into. "note" is generic guidance for the idea step.
KIND_TARGETS: dict[str, tuple[str, ...]] = {
    "note": ("idea",), "memory": ("idea", "code"), "constraint": ("idea", "code", "fix"), "skill": ("code", "fix"),
}
MAX_ENTRIES = 40


class HarnessEntry(BaseModel):
    id: str
    kind: EntryKind = "note"
    text: str
    targets: list[str] = Field(default_factory=list)   # prompt names; empty = KIND_TARGETS[kind]
    source_run: str = ""
    created: str = ""
    updated: str = ""
    uses: int = 0

    def prompts(self) -> tuple[str, ...]:
        return tuple(self.targets) or KIND_TARGETS.get(self.kind, ("idea",))


class Edit(BaseModel):
    op: Literal["create", "update", "delete"]
    id: str
    kind: EntryKind = "note"
    text: str = ""
    targets: list[str] = Field(default_factory=list)
    reason: str = ""


class Refinement(BaseModel):
    """One applied batch of edits, with the state needed to undo it."""

    event_id: str
    run: str
    trigger: str = "manual"          # manual | auto
    created: str = ""
    edits: list[Edit] = Field(default_factory=list)
    before: dict[str, HarnessEntry | None] = Field(default_factory=dict)
    after: dict[str, HarnessEntry | None] = Field(default_factory=dict)
    rolled_back: bool = False


class HarnessState(BaseModel):
    version: int = 1
    entries: dict[str, HarnessEntry] = Field(default_factory=dict)
    refinements: list[Refinement] = Field(default_factory=list)


class Harness:
    """File-backed ``HarnessState``. Reloads before every write so concurrent writers do not clobber."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> HarnessState:
        if not self.path.exists():
            return HarnessState()
        try:
            return HarnessState.model_validate_json(self.path.read_text())
        except ValueError:
            return HarnessState()

    def _save(self, state: HarnessState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(indent=1))
        tmp.replace(self.path)

    def entries_for(self, prompt: str) -> list[HarnessEntry]:
        return [e for e in self.load().entries.values() if prompt in e.prompts()]

    def text_for(self, prompt: str) -> str:
        rows = [f"- {e.text}" for e in self.entries_for(prompt)]
        return "\n".join(rows) or "- (none yet)"

    def apply(self, edits: list[Edit], run: str = "", trigger: str = "manual") -> Refinement:
        """Apply a bounded batch of edits and record it for rollback."""
        with self._lock:
            state = self.load()
            now = datetime.now(UTC).isoformat(timespec="seconds")
            ev = Refinement(event_id=f"r{uuid.uuid4().hex[:10]}", run=run, trigger=trigger, created=now, edits=edits)
            for e in edits:
                ev.before[e.id] = state.entries.get(e.id)
                if e.op == "delete":
                    state.entries.pop(e.id, None)
                    ev.after[e.id] = None
                    continue
                old = state.entries.get(e.id)
                entry = HarnessEntry(id=e.id, kind=e.kind, text=e.text.strip(), targets=e.targets,
                                     source_run=run, created=(old.created if old else now), updated=now,
                                     uses=(old.uses if old else 0))
                state.entries[e.id] = entry
                ev.after[e.id] = entry
            # keep the ledger bounded: drop the oldest entries first
            if len(state.entries) > MAX_ENTRIES:
                for k in sorted(state.entries, key=lambda k: state.entries[k].updated)[:len(state.entries) - MAX_ENTRIES]:
                    state.entries.pop(k)
            state.refinements.append(ev)
            self._save(state)
            return ev

    def rollback(self, event_id: str) -> bool:
        with self._lock:
            state = self.load()
            ev = next((r for r in state.refinements if r.event_id == event_id and not r.rolled_back), None)
            if ev is None:
                return False
            for eid, before in ev.before.items():
                if before is None:
                    state.entries.pop(eid, None)
                else:
                    state.entries[eid] = before
            ev.rolled_back = True
            self._save(state)
            return True

    def summary(self) -> str:
        state = self.load()
        rows = [f"{e.id} [{e.kind}->{','.join(e.prompts())}] {e.text[:100]}" for e in state.entries.values()]
        live = [r for r in state.refinements if not r.rolled_back]
        return "\n".join(rows) + f"\n({len(state.entries)} entries, {len(live)} refinements applied)"


def parse_edits(payload: dict[str, Any] | None, limit: int = 8) -> list[Edit]:
    """Validate a model-proposed plan: ``{"edits": [{op, id, kind, text, targets, reason}, ...]}``."""
    if not payload:
        return []
    out: list[Edit] = []
    for raw in (payload.get("edits") or [])[:limit]:
        if not isinstance(raw, dict):
            continue
        try:
            e = Edit.model_validate({k: v for k, v in raw.items() if k in Edit.model_fields})
        except ValueError:
            continue
        if not e.id or (e.op != "delete" and not e.text.strip()):
            continue
        e.targets = [t for t in e.targets if t in ("idea", "code", "fix", "tests", "judge")]
        out.append(e)
    return out


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
