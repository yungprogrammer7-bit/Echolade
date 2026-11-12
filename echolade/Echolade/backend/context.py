"""Application context: one place that wires services together."""
from __future__ import annotations

from dataclasses import dataclass

from .audio.generator import JobManager
from .config import Paths
from .engines.base import RuntimeConfig
from .engines.engine_manager import EngineManager
from .hardware_detection import HardwareInfo
from .security import SecurityConfig
from .services.history_service import HistoryService
from .services.metrics_service import MetricsService
from .services.performance_service import resolve_runtime_config
from .services.settings_service import SettingsService
from .services.storage_service import StorageService
from .services.voice_service import VoiceService


@dataclass
class AppContext:
    paths: Paths
    security: SecurityConfig
    hardware: HardwareInfo
    settings: SettingsService
    history: HistoryService
    metrics: MetricsService
    engines: EngineManager
    voices: VoiceService
    storage: StorageService
    jobs: JobManager

    def runtime(self) -> RuntimeConfig:
        return resolve_runtime_config(self.settings.get(), self.hardware)
