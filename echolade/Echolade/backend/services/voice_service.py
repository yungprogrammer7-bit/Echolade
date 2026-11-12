"""Voice discovery and locally generated previews (spec 6)."""
from __future__ import annotations

import os
import threading

import numpy as np
import soundfile as sf

from ..config import Paths
from ..engines.base import EngineError
from ..engines.engine_manager import EngineManager
from ..errors import NotFoundError

PREVIEW_TEXT = {
    "en-us": "Hello, this is a preview of this voice.",
    "en-gb": "Hello, this is a preview of this voice.",
    "es": "Hola, esta es una muestra de esta voz.",
    "fr-fr": "Bonjour, voici un aperçu de cette voix.",
    "it": "Ciao, questa è un'anteprima di questa voce.",
    "pt-br": "Olá, esta é uma prévia desta voz.",
    "hi": "नमस्ते, यह इस आवाज़ का एक नमूना है।",
    "ja": "こんにちは、これはこの声のサンプルです。",
    "cmn": "你好，这是这个声音的试听。",
}


class VoiceService:
    def __init__(self, paths: Paths, engines: EngineManager, get_runtime) -> None:
        self.dir = paths.preview_cache
        self.engines = engines
        self._get_runtime = get_runtime
        self._lock = threading.Lock()

    def catalogue(self) -> dict:
        voices = [v.to_dict() for v in self.engines.all_voices()]
        langs: dict[str, dict] = {}
        for v in voices:
            key = (v["engine"], v["language"])
            entry = langs.setdefault(key, {"engine": v["engine"], "code": v["language"],
                                           "label": v["language_label"], "count": 0})
            entry["count"] += 1
        return {"voices": voices, "languages": sorted(langs.values(), key=lambda x: x["label"])}

    def preview(self, engine_id: str, voice_id: str) -> str:
        """Return the cached preview filename, generating it locally if needed."""
        engine = self.engines.get(engine_id)
        voice = next((v for v in engine.list_voices() if v.id == voice_id), None)
        if voice is None:
            raise NotFoundError("That voice is not available.")
        name = f"{engine_id}-{voice_id}.wav"
        path = self.dir / name
        if path.is_file():
            return name
        with self._lock:
            if path.is_file():
                return name
            self.engines.ensure_loaded(engine_id, self._get_runtime())
            text = PREVIEW_TEXT.get(voice.language, PREVIEW_TEXT["en-us"])
            audio, sr = engine.synthesize(text, voice_id, 1.0)
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(name + ".part")
            try:
                sf.write(str(tmp), np.asarray(audio, dtype=np.float32), sr, subtype="PCM_16",
                         format="WAV")
                os.replace(tmp, path)
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                raise EngineError("The preview could not be saved.") from exc
        return name
