"""Measured generation metrics (spec 4.9). Nothing here is estimated or invented."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import Paths

MAX_LINES = 500


class MetricsService:
    def __init__(self, paths: Paths) -> None:
        self._path: Path = paths.data / "metrics.jsonl"
        self._lock = threading.Lock()

    def record(self, entry: dict) -> None:
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                lines = self._path.read_text(encoding="utf-8").splitlines()
                if len(lines) > MAX_LINES * 2:
                    self._path.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
            except OSError:
                pass  # metrics must never break generation

    def recent(self, limit: int = 30) -> list[dict]:
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return list(reversed(out))

    def summary(self) -> list[dict]:
        groups: dict[tuple, dict] = {}
        for m in self.recent(MAX_LINES):
            key = (m.get("engine"), m.get("profile"))
            g = groups.setdefault(key, {"engine": key[0], "profile": key[1], "runs": 0,
                                        "failures": 0, "_rtf": [], "_first": []})
            g["runs"] += 1
            g["failures"] += int(m.get("failed_segments", 0) > 0 or m.get("status") == "failed")
            if m.get("rtf") is not None:
                g["_rtf"].append(m["rtf"])
            if m.get("first_audio_s") is not None:
                g["_first"].append(m["first_audio_s"])
        out = []
        for g in groups.values():
            rtf, first = g.pop("_rtf"), g.pop("_first")
            g["avg_rtf"] = round(sum(rtf) / len(rtf), 3) if rtf else None
            g["avg_first_audio_s"] = round(sum(first) / len(first), 2) if first else None
            out.append(g)
        return out
