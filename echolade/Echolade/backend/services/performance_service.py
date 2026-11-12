"""Performance profiles, hardware-aware configuration and benchmarking (spec 4)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..engines.base import RuntimeConfig
from ..engines.engine_manager import EngineManager
from ..hardware_detection import HardwareInfo
from ..validation import UserSettings


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    description: str


PROFILES = [
    Profile("automatic", "Automatic",
            "Chooses settings from this computer's cores and memory. Uses your benchmark "
            "result if you have run one. Recommended."),
    Profile("fastest", "Fastest",
            "Uses all physical CPU cores for the quickest generation. Other apps may feel "
            "slower while it runs."),
    Profile("balanced", "Balanced",
            "Uses about half your CPU cores so the computer stays comfortable to use."),
    Profile("high_quality", "High quality",
            "Longer text segments, so there are fewer joins between segments. Same model; "
            "slower to start playing."),
    Profile("low_memory", "Low memory",
            "Fewest threads, smaller segments, and the model is unloaded after a short "
            "idle period to free RAM."),
    Profile("custom", "Custom", "Choose the number of CPU threads yourself."),
]


def resolve_runtime_config(settings: UserSettings, hw: HardwareInfo) -> RuntimeConfig:
    phys = max(1, hw.physical_cores)
    logical = max(1, hw.logical_cores)
    pid = settings.profile
    accel = bool(settings.use_acceleration and hw.acceleration_providers)
    base = dict(inter_op_threads=1, use_acceleration=accel, profile=pid)

    if pid == "fastest":
        return RuntimeConfig(intra_op_threads=min(phys, 16), memory_arena=True,
                             max_chunk_chars=500, first_chunk_chars=200,
                             reason=f"All {min(phys, 16)} physical cores.", **base)
    if pid == "balanced":
        t = min(4, max(1, math.ceil(phys / 2)))
        return RuntimeConfig(intra_op_threads=t, memory_arena=True, max_chunk_chars=500,
                             first_chunk_chars=220, reason=f"{t} of {phys} physical cores.", **base)
    if pid == "high_quality":
        t = min(4, max(1, math.ceil(phys / 2)))
        return RuntimeConfig(intra_op_threads=t, memory_arena=True, max_chunk_chars=800,
                             first_chunk_chars=260, reason=f"{t} threads, long segments.", **base)
    if pid == "low_memory":
        t = 1 if phys <= 2 else 2
        return RuntimeConfig(intra_op_threads=t, memory_arena=False, max_chunk_chars=300,
                             first_chunk_chars=150, unload_after_idle_s=30,
                             reason=f"{t} thread(s); model unloads after 30 s idle.", **base)
    if pid == "custom":
        t = max(1, min(settings.custom_threads, logical))
        return RuntimeConfig(intra_op_threads=t, memory_arena=True, max_chunk_chars=500,
                             first_chunk_chars=220, reason=f"{t} threads (your setting).", **base)

    # automatic
    low_ram = hw.ram_total_mb < 3500
    if settings.benchmark_threads:
        t = max(1, min(settings.benchmark_threads, logical))
        why = f"{t} thread(s), the fastest setting measured on this computer."
    elif phys <= 2:
        t = phys
        why = f"{t} thread(s) for a {phys}-core CPU; process priority is lowered to keep the PC responsive."
    else:
        t = min(phys - 1, 8)
        why = f"{t} of {phys} cores, leaving one free for the system."
    if low_ram:
        why += " Low RAM detected: memory-saving mode on."
    return RuntimeConfig(intra_op_threads=t, memory_arena=not low_ram, max_chunk_chars=500,
                         first_chunk_chars=220, unload_after_idle_s=120 if low_ram else None,
                         reason=why, **base)


BENCH_TEXT = ("The quick brown fox jumps over the lazy dog, and then walks calmly back "
              "through the quiet garden.")


def run_benchmark(engines: EngineManager, engine_id: str, hw: HardwareInfo,
                  voice_id: str = "af_heart") -> dict:
    """Measure real-time factor for several thread counts. Everything is measured."""
    engine = engines.get(engine_id)
    ok, reason = engine.availability()
    if not ok:
        raise RuntimeError(reason or "Engine unavailable.")

    phys, logical = max(1, hw.physical_cores), max(1, hw.logical_cores)
    counts = sorted({1, max(1, phys // 2), max(1, phys - 1), phys} & set(range(1, logical + 1)))
    candidates = [(n, False) for n in counts]
    results = []
    with engine.lock:
        for threads, accel in candidates:
            cfg = RuntimeConfig(intra_op_threads=threads, use_acceleration=accel)
            try:
                load_s = engine.load(cfg)
                engine.synthesize("Warm up.", voice_id, 1.0)  # first run includes one-off setup
                rtfs = []
                for _ in range(2):
                    t0 = time.perf_counter()
                    audio, sr = engine.synthesize(BENCH_TEXT, voice_id, 1.0)
                    rtfs.append((time.perf_counter() - t0) / (len(audio) / sr))
                results.append({"threads": threads, "rtf": round(min(rtfs), 3),
                                "load_s": round(load_s, 2), "ok": True})
            except Exception as exc:  # a failing candidate is a result, not a crash
                results.append({"threads": threads, "ok": False, "error": str(exc)[:120]})
        engine.unload()

    good = [r for r in results if r["ok"]]
    if not good:
        raise RuntimeError("The benchmark could not run on this computer.")
    best = min(r["rtf"] for r in good)
    # Prefer fewer threads when within 8% of the best: leaves CPU free for the rest of the PC.
    pick = min((r for r in good if r["rtf"] <= best * 1.08), key=lambda r: r["threads"])
    return {"engine": engine_id, "results": results, "recommended_threads": pick["threads"],
            "best_rtf": best,
            "note": "Real-time factor = generation time / audio length; below 1 is faster than playback."}
