"""Background speech-generation jobs (spec 4.6, 4.8, 14).

One worker thread runs jobs one at a time (a single model instance is the
efficient choice on ordinary PCs). The UI polls job state, so the interface is
never blocked. Completed segments are written to disk as they finish, so a
cancel or a failed segment never throws away finished work.
"""
from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf

from . import conversion
from .text import chunk_text
from ..config import LIMITS, Paths
from ..engines.base import EngineError, RuntimeConfig
from ..engines.engine_manager import EngineManager
from ..errors import BusyError, ConflictError, NotFoundError, TooLargeError, UserError
from ..services.history_service import HistoryService
from ..services.metrics_service import MetricsService
from ..validation import JobRequest, normalize_text, safe_filename

log = logging.getLogger("echolade.jobs")

SENTENCE_GAP_MS = 250
PEAK_BUCKETS = 120
MIN_FREE_DISK_MB = 200
FINISHED = {"done", "partial", "cancelled", "failed"}


@dataclass
class ChunkState:
    index: int
    text: str
    paragraph_end: bool
    status: str = "pending"  # pending | running | done | failed
    error: str | None = None
    duration: float | None = None
    synth_s: float = 0.0
    sample_rate: int | None = None


@dataclass
class Job:
    id: str
    request: JobRequest
    display_name: str
    chunks: list[ChunkState]
    directory: Path
    status: str = "queued"  # queued | running | done | partial | cancelled | failed
    phase: str = "queued"
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    result: dict | None = None
    first_audio_s: float | None = None
    init_s: float | None = None
    synth_s_total: float = 0.0
    wall_s: float = 0.0
    cpu_s: float = 0.0
    peak_rss_mb: float = 0.0
    profile: str = "automatic"
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def can_retry_now(self) -> bool:
        return self.status in ("partial", "failed", "cancelled") and \
            any(c.status in ("failed", "pending") for c in self.chunks)

    def chunk_path(self, index: int) -> Path:
        return self.directory / f"{index:05d}.wav"

    def to_public(self) -> dict:
        with self.lock:
            done = [c for c in self.chunks if c.status == "done"]
            failed = [c for c in self.chunks if c.status == "failed"]
            total = len(self.chunks)
            eta = None
            if self.status == "running" and done:
                chars_done = sum(len(c.text) for c in done)
                secs = sum(c.synth_s for c in done)
                remaining = sum(len(c.text) for c in self.chunks if c.status in ("pending", "running"))
                if chars_done and secs:
                    eta = round(secs / chars_done * remaining, 1)
            return {
                "id": self.id, "status": self.status, "phase": self.phase,
                "name": self.display_name, "error": self.error,
                "cancelling": self.cancel.is_set() and self.status == "running",
                "progress": {"done": len(done), "failed": len(failed), "total": total,
                             "fraction": round(len(done) / total, 4) if total else 0},
                "chunks": [{"i": c.index, "status": c.status, "chars": len(c.text),
                            "preview": c.text[:70], "duration": c.duration, "error": c.error}
                           for c in self.chunks],
                "ready_seconds": round(sum(c.duration or 0 for c in done), 2),
                "eta_s": eta,
                "elapsed_s": round((self.finished or time.time()) - self.started, 1)
                if self.started else 0,
                "can_retry": self.status in ("partial", "failed", "cancelled")
                and any(c.status in ("failed", "pending") for c in self.chunks),
                "can_finalize": self.status in ("partial", "cancelled") and bool(done),
                "result": self.result,
                "metrics": self.metrics(),
            }

    def metrics(self) -> dict:
        audio_s = sum(c.duration or 0 for c in self.chunks if c.status == "done")
        return {
            "init_s": round(self.init_s, 2) if self.init_s else None,
            "first_audio_s": round(self.first_audio_s, 2) if self.first_audio_s else None,
            "generation_s": round(self.synth_s_total, 2),
            "audio_s": round(audio_s, 2),
            "rtf": round(self.synth_s_total / audio_s, 3) if audio_s else None,
            "cpu_cores_avg": round(self.cpu_s / self.wall_s, 2) if self.wall_s else None,
            "peak_rss_mb": round(self.peak_rss_mb) if self.peak_rss_mb else None,
        }


class JobManager:
    def __init__(self, paths: Paths, engines: EngineManager, history: HistoryService,
                 metrics: MetricsService, get_runtime) -> None:
        self.paths = paths
        self.engines = engines
        self.history = history
        self.metrics = metrics
        self._get_runtime = get_runtime  # () -> RuntimeConfig
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._proc = psutil.Process()
        shutil.rmtree(paths.job_cache, ignore_errors=True)  # stale temp data from a past run
        paths.job_cache.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._loop, name="echolade-worker", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ API
    def submit(self, req: JobRequest, runtime: RuntimeConfig) -> Job:
        text = normalize_text(req.text)
        if not text:
            raise UserError("Your script is empty. Add some text first.")
        if len(text) > LIMITS.max_text_chars:
            raise TooLargeError(f"This script is too long ({len(text):,} characters). "
                                f"The limit is {LIMITS.max_text_chars:,}; please split it.")
        chunks = chunk_text(text, runtime.max_chunk_chars, runtime.first_chunk_chars)
        if not chunks:
            raise UserError("Your script has no readable text.")
        if len(chunks) > LIMITS.max_chunks:
            raise TooLargeError("This script has too many segments. Please split it.")
        free_mb = shutil.disk_usage(self.paths.outputs).free / (1024 * 1024)
        if free_mb < MIN_FREE_DISK_MB:
            raise UserError("There is not enough free disk space to generate audio.")
        with self._lock:
            active = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if active >= LIMITS.max_queued_jobs:
                raise BusyError("Echolade is already working on other requests. Please wait.")
            jid = uuid.uuid4().hex
            job = Job(
                id=jid, request=req,
                display_name=" ".join(req.name.split())[:LIMITS.max_name_chars] or "Voiceover",
                chunks=[ChunkState(c.index, c.text, c.paragraph_end) for c in chunks],
                directory=self.paths.job_cache / jid, profile=runtime.profile,
            )
            job.directory.mkdir(parents=True, exist_ok=True)
            self._jobs[jid] = job
            self._evict()
        self._queue.put(("run", job))
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if not job:
            raise NotFoundError("That job no longer exists.")
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        with job.lock:
            if job.status == "queued":
                job.cancel.set()
                job.status, job.phase, job.finished = "cancelled", "cancelled", time.time()
            elif job.status == "running":
                job.cancel.set()  # stops after the segment currently being synthesised
            else:
                raise ConflictError("This job is not running.")
        return job

    def retry(self, job_id: str) -> Job:
        """Re-run failed segments, or resume segments left pending by a cancel."""
        job = self.get(job_id)
        with job.lock:
            if not job.can_retry_now():
                raise ConflictError("There is nothing to retry.")
            for c in job.chunks:
                if c.status == "failed":
                    c.status, c.error = "pending", None
            job.cancel.clear()
            job.status, job.phase, job.error, job.finished = "queued", "queued", None, None
            job.directory.mkdir(parents=True, exist_ok=True)
        self._queue.put(("run", job))
        return job

    def finalize(self, job_id: str) -> Job:
        """Export whatever segments finished (after a cancel or failures)."""
        job = self.get(job_id)
        with job.lock:
            if job.status not in ("partial", "cancelled") or not any(c.status == "done" for c in job.chunks):
                raise ConflictError("There are no finished segments to export.")
            job.status, job.phase, job.finished = "queued", "queued", None
        self._queue.put(("finalize", job))
        return job

    def warmup(self) -> None:
        self._queue.put(("warmup", None))

    def active_ids(self) -> set[str]:
        with self._lock:
            return {j.id for j in self._jobs.values()}

    def is_busy(self) -> bool:
        with self._lock:
            return any(j.status in ("queued", "running") for j in self._jobs.values())

    def shutdown(self) -> None:
        self._stop.set()
        self._queue.put(("stop", None))

    # ------------------------------------------------------------- internals
    def _evict(self) -> None:
        finished = sorted((j for j in self._jobs.values() if j.status in FINISHED),
                          key=lambda j: j.created)
        while len(self._jobs) > LIMITS.max_kept_jobs and finished:
            old = finished.pop(0)
            shutil.rmtree(old.directory, ignore_errors=True)
            self._jobs.pop(old.id, None)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                mode, job = self._queue.get(timeout=5)
            except queue.Empty:
                try:
                    rt = self._get_runtime()
                    if rt.unload_after_idle_s:
                        self.engines.unload_if_idle(rt.unload_after_idle_s)
                except Exception:
                    log.exception("idle check failed")
                continue
            if mode == "stop":
                return
            try:
                if mode == "warmup":
                    self.engines.ensure_loaded("kokoro", self._get_runtime())
                elif job is not None and job.status != "cancelled":
                    if mode == "run":
                        self._run(job)
                    elif mode == "finalize":
                        self._finalize(job)
            except Exception:
                log.exception("Unhandled job error")
                if job is not None:
                    self._fail(job, "Something unexpected went wrong. Your text is safe; please try again.")

    def _fail(self, job: Job, message: str) -> None:
        with job.lock:
            job.status, job.phase, job.error, job.finished = "failed", "failed", message, time.time()
        self._record_metrics(job)

    def _sample_resources(self, job: Job) -> None:
        try:
            job.peak_rss_mb = max(job.peak_rss_mb, self._proc.memory_info().rss / (1024 * 1024))
        except psutil.Error:
            pass

    def _run(self, job: Job) -> None:
        req, d = job.request, job.request.delivery
        runtime = self._get_runtime()
        job.profile = runtime.profile
        with job.lock:
            job.status, job.phase = "running", "loading_model"
            job.started = job.started or time.time()
        t_start = time.perf_counter()
        cpu0 = self._proc.cpu_times()
        try:
            init = self.engines.ensure_loaded(req.engine, runtime)
        except EngineError as exc:
            self._fail(job, str(exc))
            return
        if init:
            job.init_s = (job.init_s or 0) + init
        engine = self.engines.get(req.engine)
        with job.lock:
            job.phase = "generating"

        for ch in job.chunks:
            if ch.status != "pending":
                continue
            if job.cancel.is_set():
                break
            with job.lock:
                ch.status = "running"
            t0 = time.perf_counter()
            try:
                audio, sr = engine.synthesize(ch.text, d.voice, d.speed)
                sf.write(str(job.chunk_path(ch.index)), audio, sr, subtype="FLOAT", format="WAV")
                with job.lock:
                    ch.status, ch.duration, ch.sample_rate = "done", len(audio) / sr, sr
                    ch.synth_s = time.perf_counter() - t0
                    job.synth_s_total += ch.synth_s
                    if job.first_audio_s is None:
                        job.first_audio_s = time.perf_counter() - t_start
            except (EngineError, OSError) as exc:
                with job.lock:
                    ch.status, ch.error = "failed", str(exc) if isinstance(exc, EngineError) \
                        else "Could not save this segment. Check free disk space."
            except Exception:
                log.exception("segment %s failed", ch.index)
                with job.lock:
                    ch.status, ch.error = "failed", "This text segment could not be converted."
            self._sample_resources(job)

        cpu1 = self._proc.cpu_times()
        job.cpu_s += (cpu1.user + cpu1.system) - (cpu0.user + cpu0.system)
        job.wall_s += time.perf_counter() - t_start
        self.engines.touch(req.engine)

        with job.lock:
            done = [c for c in job.chunks if c.status == "done"]
            failed = [c for c in job.chunks if c.status == "failed"]
            if job.cancel.is_set():
                job.status, job.phase, job.finished = "cancelled", "cancelled", time.time()
                if not done:
                    shutil.rmtree(job.directory, ignore_errors=True)
                return
            if failed and not done:
                job.status, job.phase, job.finished = "failed", "failed", time.time()
                job.error = failed[0].error or "Speech generation failed."
        if job.status == "failed":
            self._record_metrics(job)
            return
        if failed:
            with job.lock:
                job.status, job.phase, job.finished = "partial", "partial", time.time()
                job.error = f"{len(failed)} segment(s) failed. Retry them, or export what finished."
            self._record_metrics(job)
            return
        self._finalize(job)

    def _finalize(self, job: Job) -> None:
        req = job.request
        with job.lock:
            job.status, job.phase = "running", "exporting"
            job.started = job.started or time.time()
            done = [c for c in job.chunks if c.status == "done"]
            missing = [c.index for c in job.chunks if c.status != "done"]
        master = job.directory / "master.wav"
        dest: Path | None = None
        try:
            if not done:
                raise conversion.ExportError("There are no finished segments to export.")
            sr = done[0].sample_rate or 24000

            # pass 1: global peak and exact length (so volume never clips)
            peak, frames, gaps = 0.0, 0, []
            for i, c in enumerate(done):
                data, csr = sf.read(str(job.chunk_path(c.index)), dtype="float32")
                if csr != sr:
                    raise conversion.ExportError("Segments have different sample rates.")
                peak = max(peak, float(np.max(np.abs(data))) if data.size else 0.0)
                frames += len(data)
                gap = 0
                if i < len(done) - 1:
                    ms = req.delivery.paragraph_pause_ms if c.paragraph_end else SENTENCE_GAP_MS
                    gap = int(sr * ms / 1000)
                gaps.append(gap)
                frames += gap
            gain = 10 ** (req.delivery.volume_db / 20)
            limited = False
            if peak * gain > 0.98:
                gain, limited = 0.98 / peak, True

            # pass 2: stream the master file and collect waveform peaks
            bounds = np.linspace(0, frames, PEAK_BUCKETS + 1).astype(np.int64)
            bucket = np.zeros(PEAK_BUCKETS, dtype=np.float32)
            offset = 0

            def note(block: np.ndarray) -> None:
                nonlocal offset
                end = offset + len(block)
                first = max(0, int(np.searchsorted(bounds, offset, side="right")) - 1)
                for b in range(first, PEAK_BUCKETS):
                    if bounds[b] >= end:
                        break
                    s, e = max(bounds[b], offset) - offset, min(bounds[b + 1], end) - offset
                    if e > s:
                        bucket[b] = max(bucket[b], float(np.max(np.abs(block[s:e]))))
                offset = end

            with sf.SoundFile(str(master), "w", samplerate=sr, channels=1, subtype="FLOAT",
                              format="WAV") as out:
                for c, gap in zip(done, gaps):
                    data, _ = sf.read(str(job.chunk_path(c.index)), dtype="float32")
                    data = data * gain
                    out.write(data)
                    note(data)
                    if gap:
                        silence = np.zeros(gap, dtype=np.float32)
                        out.write(silence)
                        note(silence)
            expected = frames / sr

            fmt = req.export.format
            base = safe_filename(job.display_name)
            dest = conversion.unique_path(self.paths.outputs, base, fmt)
            conversion.export_audio(
                master, dest, fmt=fmt, native_rate=sr, sample_rate=req.export.sample_rate,
                channels=req.export.channels, mp3_bitrate=req.export.mp3_bitrate,
                title=job.display_name)
            actual = conversion.validate_output(dest, expected, fmt)

            top = float(bucket.max()) or 1.0
            peaks = [max(3, int(round(v / top * 100))) for v in bucket]
            d_voice = req.delivery.voice
            entry = {
                "id": uuid.uuid4().hex, "name": job.display_name, "file": dest.name,
                "format": fmt, "voice": d_voice, "voice_name": d_voice[3:].replace("_", " ").title(),
                "engine": req.engine, "duration_s": round(actual, 2),
                "size_bytes": dest.stat().st_size, "sample_rate": req.export.sample_rate,
                "channels": req.export.channels,
                "bitrate": req.export.mp3_bitrate if fmt == "mp3" else None,
                "status": "partial" if missing else "complete",
                "missing_segments": missing, "segments": len(job.chunks),
                "chars": sum(len(c.text) for c in job.chunks), "profile": job.profile,
                "volume_limited": limited, "peaks": peaks,
            }
            entry = self.history.add(entry)
            with job.lock:
                job.result = entry
                job.status = "partial" if missing else "done"
                job.phase = job.status
                job.error = (f"{len(missing)} segment(s) are missing from this export."
                             if missing else None)
                job.finished = time.time()
            if not missing:
                shutil.rmtree(job.directory, ignore_errors=True)  # chunks no longer needed
            else:
                master.unlink(missing_ok=True)
        except conversion.ExportError as exc:
            if dest is not None:
                dest.unlink(missing_ok=True)  # never leave a file that failed validation
            master.unlink(missing_ok=True)
            with job.lock:
                job.status, job.phase, job.error, job.finished = "partial", "partial", str(exc), time.time()
            self._record_metrics(job)
            return
        self._record_metrics(job)

    def _record_metrics(self, job: Job) -> None:
        m = job.metrics()
        self.metrics.record({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "engine": job.request.engine,
            "profile": job.profile, "status": job.status, "segments": len(job.chunks),
            "failed_segments": sum(1 for c in job.chunks if c.status == "failed"),
            "chars": sum(len(c.text) for c in job.chunks), **m,
        })
