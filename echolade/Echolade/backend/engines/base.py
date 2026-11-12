"""Engine adapter contract (spec 3.3).

Every speech engine implements ``TTSEngine``. The rest of the application only
talks to this interface, so engines can be added or swapped without touching
the API, job runner or UI.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    engine: str
    language: str          # engine language code, e.g. "en-us"
    language_label: str    # human label, e.g. "American English"
    gender: str | None     # "female" / "male" when the engine's naming states it
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Capabilities:
    speed: bool = True
    pitch: bool = False
    emphasis: bool = False
    expressive_styles: bool = False
    streaming: bool = False  # True only for genuinely incremental audio output

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeConfig:
    """Resource settings an engine applies when it loads."""

    intra_op_threads: int = 1
    inter_op_threads: int = 1
    memory_arena: bool = True
    use_acceleration: bool = False
    max_chunk_chars: int = 500
    first_chunk_chars: int = 220
    unload_after_idle_s: int | None = None
    profile: str = "automatic"
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def engine_key(self) -> tuple:
        """Fields that require a model reload when changed."""
        return (self.intra_op_threads, self.inter_op_threads,
                self.memory_arena, self.use_acceleration)


@dataclass
class EngineStatus:
    id: str
    name: str
    description: str
    available: bool
    loaded: bool
    reason: str | None = None
    capabilities: dict = field(default_factory=dict)
    sample_rate: int | None = None
    provider: str | None = None
    load_seconds: float | None = None


class EngineError(Exception):
    """An error whose message is safe to show to the user."""


class TTSEngine(ABC):
    id: str
    name: str
    description: str
    capabilities: Capabilities = Capabilities()

    def __init__(self) -> None:
        self.lock = threading.RLock()  # one inference at a time per engine

    @abstractmethod
    def availability(self) -> tuple[bool, str | None]:
        """(available, reason-if-not). Must be cheap and never raise."""

    @abstractmethod
    def load(self, config: RuntimeConfig) -> float:
        """Load the model. Returns seconds taken. Raises EngineError."""

    @abstractmethod
    def unload(self) -> None: ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def list_voices(self) -> list[Voice]: ...

    @abstractmethod
    def synthesize(self, text: str, voice_id: str, speed: float) -> tuple[np.ndarray, int]:
        """Return mono float32 audio in [-1, 1] and its sample rate."""

    @abstractmethod
    def status(self) -> EngineStatus: ...
