"""Input validation. All request data is untrusted (spec 13.2)."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import LIMITS

VOICE_ID_RE = re.compile(r"^[a-z]{2}_[a-z0-9]{1,30}$")
ENGINE_ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")

_RESERVED_WIN = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


def safe_filename(name: str, default: str = "echolade-voiceover") -> str:
    """Return a file-system-safe base name (no extension, no path parts).

    Never trusts the caller: strips path separators, control characters,
    Windows-reserved names and trailing dots/spaces, and caps the length.
    """
    name = unicodedata.normalize("NFKC", str(name or ""))
    name = _BAD_CHARS.sub("-", name)
    name = re.sub(r"\s+", " ", name).strip(" .-_")
    name = re.sub(r"-{2,}", "-", name)
    if name.split(".")[0].upper() in _RESERVED_WIN:
        name = f"{name}-audio"
    return (name[: LIMITS.max_name_chars].strip(" .-_")) or default


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(text: str) -> str:
    """Non-semantic clean-up only: line endings, control chars, whitespace runs.

    It never rewrites words, numbers or punctuation (spec 5.3).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTRL.sub("", text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class DeliverySettings(BaseModel):
    voice: str = Field(default="af_heart", max_length=40)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    volume_db: float = Field(default=0.0, ge=-12.0, le=6.0)
    paragraph_pause_ms: int = Field(default=700, ge=0, le=3000)

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str) -> str:
        if not VOICE_ID_RE.match(v):
            raise ValueError("Invalid voice identifier.")
        return v


class ExportSettings(BaseModel):
    format: Literal["wav", "mp3"] = "mp3"
    mp3_bitrate: Literal[96, 128, 192, 256] = 192
    sample_rate: Literal[24000, 44100, 48000] = 24000
    channels: Literal[1, 2] = 1


class JobRequest(BaseModel):
    text: str = Field(min_length=1, max_length=LIMITS.max_text_chars * 2)
    name: str = Field(default="echolade-voiceover", max_length=200)
    engine: str = "kokoro"
    delivery: DeliverySettings = DeliverySettings()
    export: ExportSettings = ExportSettings()

    @field_validator("engine")
    @classmethod
    def _engine(cls, v: str) -> str:
        if not ENGINE_ID_RE.match(v):
            raise ValueError("Invalid engine identifier.")
        return v


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


Theme = Literal["system", "light", "dark"]
ProfileId = Literal["automatic", "fastest", "balanced", "high_quality", "low_memory", "custom"]


class UserSettings(BaseModel):
    theme: Theme = "system"
    default_voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    volume_db: float = Field(default=0.0, ge=-12.0, le=6.0)
    paragraph_pause_ms: int = Field(default=700, ge=0, le=3000)
    format: Literal["wav", "mp3"] = "mp3"
    mp3_bitrate: Literal[96, 128, 192, 256] = 192
    sample_rate: Literal[24000, 44100, 48000] = 24000
    channels: Literal[1, 2] = 1
    profile: ProfileId = "automatic"
    custom_threads: int = Field(default=2, ge=1, le=64)
    use_acceleration: bool = False
    warmup: bool = False
    favourites: list[str] = Field(default_factory=list, max_length=LIMITS.max_favourites)
    recent_voices: list[str] = Field(default_factory=list, max_length=8)
    benchmark_threads: int | None = Field(default=None, ge=1, le=64)

    @field_validator("default_voice")
    @classmethod
    def _dv(cls, v: str) -> str:
        if not VOICE_ID_RE.match(v):
            raise ValueError("Invalid voice identifier.")
        return v

    @field_validator("favourites", "recent_voices")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        for item in v:
            if not VOICE_ID_RE.match(item):
                raise ValueError("Invalid voice identifier in list.")
        return list(dict.fromkeys(v))  # de-duplicate, keep order


class SettingsPatch(BaseModel):
    """Partial update: only provided keys are applied, each re-validated."""

    model_config = {"extra": "forbid"}
    theme: Theme | None = None
    default_voice: str | None = None
    speed: float | None = None
    volume_db: float | None = None
    paragraph_pause_ms: int | None = None
    format: Literal["wav", "mp3"] | None = None
    mp3_bitrate: Literal[96, 128, 192, 256] | None = None
    sample_rate: Literal[24000, 44100, 48000] | None = None
    channels: Literal[1, 2] | None = None
    profile: ProfileId | None = None
    custom_threads: int | None = None
    use_acceleration: bool | None = None
    warmup: bool | None = None
    favourites: list[str] | None = None
    recent_voices: list[str] | None = None
    benchmark_threads: int | None = None
