"""Kokoro ONNX engine (primary engine)."""
from __future__ import annotations

import logging
import time

import numpy as np

from .base import Capabilities, EngineError, EngineStatus, RuntimeConfig, TTSEngine, Voice
from ..config import Paths
from ..hardware_detection import BLOCKED_PROVIDERS

log = logging.getLogger("echolade.kokoro")

MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

# Kokoro voice ids are "<lang><gender>_<name>"; these are the model's own prefixes.
_LANGS = {
    "a": ("en-us", "American English"),
    "b": ("en-gb", "British English"),
    "e": ("es", "Spanish"),
    "f": ("fr-fr", "French"),
    "h": ("hi", "Hindi"),
    "i": ("it", "Italian"),
    "j": ("ja", "Japanese"),
    "p": ("pt-br", "Brazilian Portuguese"),
    "z": ("cmn", "Mandarin Chinese"),
}
# Languages whose phonemisation path is the most limited in this build.
LIMITED_LANGS = {"ja", "cmn", "hi"}


def parse_voice(voice_id: str, engine_id: str = "kokoro") -> Voice | None:
    if len(voice_id) < 4 or voice_id[0] not in _LANGS or voice_id[1] not in "fm" or voice_id[2] != "_":
        return None
    code, label = _LANGS[voice_id[0]]
    gender = "female" if voice_id[1] == "f" else "male"
    note = " · limited phonemiser support" if code in LIMITED_LANGS else ""
    return Voice(
        id=voice_id, name=voice_id[3:].replace("_", " ").title(), engine=engine_id,
        language=code, language_label=label, gender=gender,
        description=f"{label} · {gender} voice{note}",
    )


class KokoroEngine(TTSEngine):
    id = "kokoro"
    name = "Kokoro ONNX"
    description = "Neural speech, 82M parameters, runs fully on this computer."
    capabilities = Capabilities(speed=True, pitch=False, emphasis=False,
                                expressive_styles=False, streaming=False)

    def __init__(self, paths: Paths) -> None:
        super().__init__()
        self._model_path = paths.models / MODEL_FILE
        self._voices_path = paths.models / VOICES_FILE
        self._kokoro = None
        self._voices: list[Voice] | None = None
        self._config: RuntimeConfig | None = None
        self._provider: str | None = None
        self._load_seconds: float | None = None
        self.sample_rate = 24000

    # -- availability -----------------------------------------------------
    def availability(self) -> tuple[bool, str | None]:
        missing = [p.name for p in (self._model_path, self._voices_path) if not p.is_file()]
        if missing:
            return False, ("Speech model files are missing (" + ", ".join(missing) +
                           "). Run the setup script to download them.")
        try:
            import kokoro_onnx  # noqa: F401
            import onnxruntime  # noqa: F401
        except Exception:
            return False, "The kokoro-onnx or onnxruntime package is not installed."
        return True, None

    @property
    def is_loaded(self) -> bool:
        return self._kokoro is not None

    @property
    def loaded_config(self) -> RuntimeConfig | None:
        return self._config

    # -- loading ----------------------------------------------------------
    def _build_session(self, config: RuntimeConfig):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = int(config.intra_op_threads)
        so.inter_op_num_threads = int(config.inter_op_threads)
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.enable_cpu_mem_arena = bool(config.memory_arena)

        candidates: list[list[str]] = []
        if config.use_acceleration:
            accel = [p for p in ort.get_available_providers()
                     if p not in BLOCKED_PROVIDERS and p != "CPUExecutionProvider"]
            if accel:
                candidates.append([accel[0], "CPUExecutionProvider"])
        candidates.append(["CPUExecutionProvider"])  # CPU is always the fallback

        last: Exception | None = None
        for providers in candidates:
            try:
                session = ort.InferenceSession(str(self._model_path), sess_options=so,
                                               providers=providers)
                return session, session.get_providers()[0]
            except Exception as exc:  # fall through to the next candidate
                log.warning("Provider %s failed: %s", providers[0], exc)
                last = exc
        raise EngineError("The speech model could not be loaded. The file may be corrupted; "
                          "re-run the setup script to download it again.") from last

    def load(self, config: RuntimeConfig) -> float:
        with self.lock:
            ok, reason = self.availability()
            if not ok:
                raise EngineError(reason or "Engine unavailable.")
            if self._kokoro is not None and self._config and \
                    self._config.engine_key() == config.engine_key():
                self._config = config
                return 0.0
            self.unload()
            from kokoro_onnx import Kokoro

            t0 = time.perf_counter()
            try:
                session, provider = self._build_session(config)
                self._kokoro = Kokoro.from_session(session, str(self._voices_path))
            except EngineError:
                raise
            except Exception as exc:
                log.exception("Kokoro load failed")
                raise EngineError("The speech model could not be loaded. The files may be "
                                  "corrupted; re-run the setup script.") from exc
            self._provider = provider
            self._config = config
            self._voices = None
            self._load_seconds = time.perf_counter() - t0
            log.info("Kokoro loaded in %.2fs (%s, %d threads)", self._load_seconds, provider,
                     config.intra_op_threads)
            return self._load_seconds

    def unload(self) -> None:
        with self.lock:
            self._kokoro = None
            self._config = None
            self._provider = None
            import gc

            gc.collect()

    # -- voices -----------------------------------------------------------
    def list_voices(self) -> list[Voice]:
        if self._voices is not None:
            return self._voices
        ok, _ = self.availability()
        if not ok:
            return []
        try:
            # Reading the voice names from the .bin archive does not need the model loaded.
            import numpy as np_

            with np_.load(str(self._voices_path)) as data:
                ids = sorted(data.files)
        except Exception:
            log.exception("Could not read voices file")
            return []
        voices = [v for v in (parse_voice(i, self.id) for i in ids) if v]
        self._voices = voices
        return voices

    # -- synthesis --------------------------------------------------------
    def synthesize(self, text: str, voice_id: str, speed: float) -> tuple[np.ndarray, int]:
        voice = parse_voice(voice_id, self.id)
        if voice is None:
            raise EngineError("That voice is not supported by this engine.")
        with self.lock:
            if self._kokoro is None:
                raise EngineError("The speech engine is not loaded.")
            try:
                audio, sr = self._kokoro.create(text, voice=voice_id, speed=float(speed),
                                                lang=voice.language)
            except Exception as exc:
                log.exception("Synthesis failed")
                raise EngineError("This text segment could not be converted to speech.") from exc
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            raise EngineError("The engine produced no audio for this segment.")
        return audio, int(sr)

    def status(self) -> EngineStatus:
        ok, reason = self.availability()
        return EngineStatus(
            id=self.id, name=self.name, description=self.description, available=ok,
            loaded=self.is_loaded, reason=reason, capabilities=self.capabilities.to_dict(),
            sample_rate=self.sample_rate, provider=self._provider,
            load_seconds=round(self._load_seconds, 2) if self._load_seconds else None,
        )
