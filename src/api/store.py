from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


class RunStore:
    """Small ignored JSON store; DataHub remains authoritative for graph receipts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = RLock()
        self._state: dict[str, Any] = {
            "schema_version": "covenant.api_state.v1",
            "changes": {},
            "runs": {},
        }
        if path and path.exists():
            self._state = json.loads(path.read_text())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def get_change(self, change_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._state["changes"].get(change_id)
            return deepcopy(value) if value else None

    def put_change(self, change_id: str, value: dict[str, Any]) -> None:
        with self._lock:
            existing = self._state["changes"].get(change_id)
            if existing and existing.get("document_hashes") != value.get("document_hashes"):
                raise ValueError("immutable change identity conflicts with stored documents")
            self._state["changes"][change_id] = deepcopy(value)
            self._persist()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._state["runs"].get(run_id)
            return deepcopy(value) if value else None

    def put_run(self, run_id: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._state["runs"][run_id] = deepcopy(value)
            self._persist()

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(self._state, indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload)
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        os.chmod(self.path, 0o600)
