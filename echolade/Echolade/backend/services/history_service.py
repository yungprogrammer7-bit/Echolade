"""Local audio history (spec 9). Stores metadata; audio files live in outputs/."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from ._jsonstore import atomic_write_json, read_json
from ..config import LIMITS, Paths

_FILE_RE = re.compile(r"^[^/\\\x00]{1,200}$")


class HistoryService:
    def __init__(self, paths: Paths) -> None:
        self._outputs = paths.outputs.resolve()
        self._path = paths.data / "history.json"
        self._lock = threading.RLock()
        data = read_json(self._path, [])
        self._entries: list[dict] = [e for e in data if isinstance(e, dict) and "id" in e] \
            if isinstance(data, list) else []

    def _save(self) -> None:
        atomic_write_json(self._path, self._entries)

    def file_path(self, entry: dict) -> Path | None:
        """Resolve an entry's file, refusing anything outside the outputs folder."""
        name = entry.get("file", "")
        if not _FILE_RE.match(name):
            return None
        p = (self._outputs / name).resolve()
        if p.parent != self._outputs:
            return None
        return p

    def _public(self, e: dict) -> dict:
        p = self.file_path(e)
        out = dict(e)
        out["file_missing"] = not (p and p.is_file())
        return out

    def list(self) -> list[dict]:
        with self._lock:
            return [self._public(e) for e in sorted(self._entries, key=lambda x: x["created_at"],
                                                    reverse=True)]

    def get(self, entry_id: str) -> dict | None:
        with self._lock:
            for e in self._entries:
                if e["id"] == entry_id:
                    return self._public(e)
        return None

    def add(self, entry: dict) -> dict:
        with self._lock:
            entry.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            self._entries.append(entry)
            self._entries.sort(key=lambda x: x["created_at"])
            if len(self._entries) > LIMITS.max_history_entries:
                self._entries = self._entries[-LIMITS.max_history_entries:]
            self._save()
            return self._public(entry)

    def rename(self, entry_id: str, name: str) -> dict | None:
        with self._lock:
            for e in self._entries:
                if e["id"] == entry_id:
                    e["name"] = name.strip()[:LIMITS.max_name_chars] or e["name"]
                    self._save()
                    return self._public(e)
        return None

    def delete(self, entry_id: str) -> bool:
        """Remove the entry and its audio file (the caller must have confirmed)."""
        with self._lock:
            for i, e in enumerate(self._entries):
                if e["id"] == entry_id:
                    p = self.file_path(e)
                    if p and p.is_file():
                        p.unlink()
                    del self._entries[i]
                    self._save()
                    return True
        return False
