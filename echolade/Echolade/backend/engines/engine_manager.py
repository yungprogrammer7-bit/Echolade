"""Registry and lifecycle for speech engines."""
from __future__ import annotations

import time

from .base import EngineError, RuntimeConfig, TTSEngine
from .kokoro_engine import KokoroEngine
from ..config import Paths


class EngineManager:
    def __init__(self, paths: Paths) -> None:
        self._engines: dict[str, TTSEngine] = {}
        self._last_used: dict[str, float] = {}
        self.register(KokoroEngine(paths))

    def register(self, engine: TTSEngine) -> None:
        self._engines[engine.id] = engine

    def ids(self) -> list[str]:
        return list(self._engines)

    def get(self, engine_id: str) -> TTSEngine:
        try:
            return self._engines[engine_id]
        except KeyError:
            raise EngineError("That speech engine is not installed.") from None

    def ensure_loaded(self, engine_id: str, config: RuntimeConfig) -> float:
        """Load (or reuse) the engine. Returns seconds spent loading, 0 if reused."""
        engine = self.get(engine_id)
        seconds = engine.load(config)
        self.touch(engine_id)
        return seconds

    def touch(self, engine_id: str) -> None:
        self._last_used[engine_id] = time.monotonic()

    def unload_if_idle(self, idle_seconds: int) -> list[str]:
        unloaded = []
        for eid, engine in self._engines.items():
            if engine.is_loaded and time.monotonic() - self._last_used.get(eid, 0) > idle_seconds:
                if engine.lock.acquire(blocking=False):
                    try:
                        engine.unload()
                        unloaded.append(eid)
                    finally:
                        engine.lock.release()
        return unloaded

    def all_voices(self):
        voices = []
        for e in self._engines.values():
            voices.extend(e.list_voices())
        return voices

    def statuses(self):
        return [e.status() for e in self._engines.values()]
