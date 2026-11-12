"""Storage usage and safe cache clearing (spec 15, Storage)."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..config import Paths


def _size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


class StorageService:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def usage(self) -> dict:
        p = self.paths
        return {
            "outputs_bytes": _size(p.outputs),
            "models_bytes": _size(p.models),
            "cache_bytes": _size(p.cache),
            "data_bytes": _size(p.data),
            "logs_bytes": _size(p.logs),
            "outputs_dir": p.outputs.name,
        }

    def clear_cache(self, keep_job_ids: set[str]) -> int:
        """Delete voice previews and finished-job temp folders. Never touches outputs/."""
        freed = 0
        for f in self.paths.preview_cache.glob("*"):
            try:
                if f.is_file():
                    freed += f.stat().st_size
                    f.unlink()
            except OSError:
                continue
        for d in self.paths.job_cache.glob("*"):
            if d.is_dir() and d.name not in keep_job_ids:
                freed += _size(d)
                shutil.rmtree(d, ignore_errors=True)
        return freed
