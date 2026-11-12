"""Best-effort hardware detection (spec 4.1).

Every probe is wrapped: if something cannot be detected it is reported as
unknown rather than guessed.
"""
from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

# Providers that must never be used for local-only speech: Azure sends data off-device.
BLOCKED_PROVIDERS = {"AzureExecutionProvider"}


@dataclass
class HardwareInfo:
    os: str
    os_version: str
    machine: str
    cpu_name: str | None
    cpu_vendor: str | None
    physical_cores: int
    logical_cores: int
    instruction_sets: dict[str, bool] = field(default_factory=dict)
    ram_total_mb: int = 0
    ram_available_mb: int = 0
    disk_free_mb: int | None = None
    providers: list[str] = field(default_factory=list)
    acceleration_providers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _cpu_name() -> str | None:
    system = platform.system()
    try:
        if system == "Linux":
            for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        elif system == "Windows":
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        elif system == "Darwin":
            return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    except Exception:
        pass
    return platform.processor() or None


def _vendor(name: str | None) -> str | None:
    if not name:
        return None
    low = name.lower()
    for key, label in (("intel", "Intel"), ("amd", "AMD"), ("apple", "Apple"),
                       ("qualcomm", "Qualcomm"), ("snapdragon", "Qualcomm")):
        if key in low:
            return label
    return None


def _instruction_sets() -> dict[str, bool]:
    wanted = {"sse4_2": "sse4_2", "avx": "avx", "avx2": "avx2", "avx512f": "avx512f"}
    system = platform.system()
    try:
        if system == "Linux":
            flags: set[str] = set()
            for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
                if line.lower().startswith(("flags", "features")):
                    flags = set(line.split(":", 1)[1].split())
                    break
            if flags:
                return {label: key in flags for label, key in wanted.items()}
        elif system == "Windows":
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            present = lambda n: bool(k32.IsProcessorFeaturePresent(n))  # noqa: E731
            # 39=AVX, 40=AVX2, 41=AVX-512F (documented PF_* constants)
            return {"avx": present(39), "avx2": present(40), "avx512f": present(41)}
        elif system == "Darwin":
            feats = (_run(["sysctl", "-n", "machdep.cpu.features"]) or "") + " " + \
                    (_run(["sysctl", "-n", "machdep.cpu.leaf7_features"]) or "")
            if feats.strip():
                up = set(feats.upper().split())
                return {"sse4_2": "SSE4.2" in up, "avx": "AVX1.0" in up,
                        "avx2": "AVX2" in up, "avx512f": "AVX512F" in up}
    except Exception:
        pass
    return {}


def detect_hardware(disk_path: Path | None = None) -> HardwareInfo:
    logical = psutil.cpu_count(logical=True) or 1
    physical = psutil.cpu_count(logical=False) or logical
    vm = psutil.virtual_memory()
    name = _cpu_name()

    disk_free = None
    try:
        disk_free = int(shutil.disk_usage(disk_path or Path.cwd()).free / (1024 * 1024))
    except Exception:
        pass

    providers: list[str] = []
    try:
        import onnxruntime as ort

        providers = [p for p in ort.get_available_providers() if p not in BLOCKED_PROVIDERS]
    except Exception:
        pass

    return HardwareInfo(
        os=platform.system(),
        os_version=platform.release(),
        machine=platform.machine(),
        cpu_name=name,
        cpu_vendor=_vendor(name),
        physical_cores=int(physical),
        logical_cores=int(logical),
        instruction_sets=_instruction_sets(),
        ram_total_mb=int(vm.total / (1024 * 1024)),
        ram_available_mb=int(vm.available / (1024 * 1024)),
        disk_free_mb=disk_free,
        providers=providers,
        acceleration_providers=[p for p in providers if p != "CPUExecutionProvider"],
    )


def lower_process_priority() -> bool:
    """Run below normal priority so the rest of the PC stays responsive (spec 4.2).

    Done once at start-up: on Linux/macOS niceness cannot be lowered again
    without privileges, and this process is a background compute service.
    """
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(5)
        return True
    except Exception:
        return False


