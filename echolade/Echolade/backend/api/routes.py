"""System, diagnostics, storage, benchmark and model-integrity endpoints."""
from __future__ import annotations

import hashlib
import json

import psutil
from fastapi import APIRouter, Request

from .deps import ctx
from ..audio.conversion import ffmpeg_available
from ..config import APP_NAME, APP_VERSION, BIND_HOST
from ..errors import ConflictError, UserError
from ..services.performance_service import PROFILES, run_benchmark

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION}


@router.get("/system")
def system(request: Request):
    c = ctx(request)
    hw = c.hardware.to_dict()
    vm = psutil.virtual_memory()
    hw["ram_available_mb"] = int(vm.available / (1024 * 1024))
    return {
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "hardware": hw,
        "runtime": c.runtime().to_dict(),
        "profiles": [p.__dict__ for p in PROFILES],
        "ffmpeg": ffmpeg_available(),
        "engines": [e.__dict__ for e in c.engines.statuses()],
        "busy": c.jobs.is_busy(),
        "network": {"bind_host": BIND_HOST, "port": c.security.port, "internet_required": False},
    }


@router.get("/diagnostics")
def diagnostics(request: Request):
    c = ctx(request)
    return {"recent": c.metrics.recent(20), "summary": c.metrics.summary()}


@router.post("/benchmark")
def benchmark(request: Request):
    c = ctx(request)
    if c.jobs.is_busy():
        raise ConflictError("Wait for the current generation to finish before benchmarking.")
    try:
        result = run_benchmark(c.engines, "kokoro", c.hardware)
    except RuntimeError as exc:
        raise UserError(str(exc)) from exc
    c.settings.update({"benchmark_threads": result["recommended_threads"]})
    return result


@router.get("/storage")
def storage(request: Request):
    return ctx(request).storage.usage()


@router.post("/storage/clear-cache")
def clear_cache(request: Request):
    c = ctx(request)
    if c.jobs.is_busy():
        raise ConflictError("Wait for the current generation to finish first.")
    freed = c.storage.clear_cache(keep_job_ids=set())
    return {"freed_bytes": freed}


@router.post("/models/verify")
def verify_models(request: Request):
    """Compare model files against the SHA-256 values pinned in model-manifest.json."""
    c = ctx(request)
    manifest_path = c.paths.root / "models" / "model-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UserError("The model manifest could not be read.") from exc
    results = []
    for f in manifest.get("files", []):
        path = c.paths.models / f["name"]
        item = {"file": f["name"], "present": path.is_file(), "ok": False}
        if path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            item["ok"] = h.hexdigest() == f["sha256"]
        results.append(item)
    return {"results": results, "all_ok": all(r["ok"] for r in results)}
