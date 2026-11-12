"""Persistent user settings, validated on every read and write."""
from __future__ import annotations

import threading

from pydantic import ValidationError

from ._jsonstore import atomic_write_json, read_json
from ..config import Paths
from ..validation import UserSettings


class SettingsService:
    def __init__(self, paths: Paths) -> None:
        self._path = paths.data / "settings.json"
        self._lock = threading.RLock()
        raw = read_json(self._path, {})
        try:
            self._settings = UserSettings(**raw) if isinstance(raw, dict) else UserSettings()
        except ValidationError:
            self._settings = UserSettings()

    def get(self) -> UserSettings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update(self, patch: dict) -> UserSettings:
        """Apply a partial update. Raises pydantic.ValidationError when invalid."""
        with self._lock:
            merged = self._settings.model_dump()
            merged.update({k: v for k, v in patch.items() if v is not None})
            new = UserSettings(**merged)
            atomic_write_json(self._path, new.model_dump())
            self._settings = new
            return new.model_copy(deep=True)

    def remember_voice(self, voice_id: str) -> None:
        s = self.get()
        recent = [voice_id] + [v for v in s.recent_voices if v != voice_id]
        self.update({"recent_voices": recent[:8]})
