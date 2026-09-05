"""Append-only run log: one JSON object per line in ``runs/<run>/events.jsonl``."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def emit(self, kind: str, **data: Any) -> None:
        row = {"t": round(time.time(), 3), "kind": kind, **data}
        with self._lock, self.path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
