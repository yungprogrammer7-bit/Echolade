"""Application paths, limits and constants.

Everything that touches the file system is rooted in a ``Paths`` object so the
app (and the tests) can be pointed at a different home directory without
changing code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Echolade"
APP_VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8765
BIND_HOST = "127.0.0.1"  # never 0.0.0.0 by default (spec 13.1)


@dataclass(frozen=True)
class Limits:
    """Hard safety limits. Every one is enforced server-side."""

    max_text_chars: int = 100_000
    max_chunks: int = 1_500
    max_name_chars: int = 80
    max_body_bytes: int = 1_000_000  # ~1 MB covers max_text_chars of any script
    max_queued_jobs: int = 3
    max_kept_jobs: int = 20
    max_history_entries: int = 500
    max_favourites: int = 200


@dataclass(frozen=True)
class Paths:
    root: Path
    models: Path
    outputs: Path
    data: Path
    cache: Path
    logs: Path
    frontend: Path

    @property
    def job_cache(self) -> Path:
        return self.cache / "jobs"

    @property
    def preview_cache(self) -> Path:
        return self.cache / "previews"

    def ensure(self) -> None:
        for p in (self.outputs, self.data, self.cache, self.logs,
                  self.job_cache, self.preview_cache):
            p.mkdir(parents=True, exist_ok=True)


def default_paths(home: Path | None = None, models: Path | None = None) -> Paths:
    """Build the path set. ``ECHOLADE_HOME`` relocates user data (not models)."""
    env_home = os.environ.get("ECHOLADE_HOME")
    base = Path(home or env_home or ROOT).resolve()
    return Paths(
        root=ROOT,
        models=Path(models or os.environ.get("ECHOLADE_MODELS_DIR") or ROOT / "models").resolve(),
        outputs=base / "outputs",
        data=base / "data",
        cache=base / "cache",
        logs=base / "logs",
        frontend=ROOT / "frontend",
    )


LIMITS = Limits()
