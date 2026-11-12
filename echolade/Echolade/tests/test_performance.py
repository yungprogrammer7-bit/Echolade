import pytest

from backend.engines.base import RuntimeConfig
from backend.hardware_detection import BLOCKED_PROVIDERS, HardwareInfo, detect_hardware
from backend.services.performance_service import PROFILES, resolve_runtime_config
from backend.validation import UserSettings
from tests.conftest import needs_model


def hw(phys=4, logical=8, ram=16000, accel=()):
    return HardwareInfo(os="Test", os_version="1", machine="x86_64", cpu_name="Test CPU",
                        cpu_vendor=None, physical_cores=phys, logical_cores=logical,
                        ram_total_mb=ram, ram_available_mb=ram // 2,
                        providers=["CPUExecutionProvider", *accel],
                        acceleration_providers=list(accel))


def cfg(profile, h, **kw):
    return resolve_runtime_config(UserSettings(profile=profile, **kw), h)


def test_hardware_detection_is_sane():
    h = detect_hardware()
    assert h.logical_cores >= h.physical_cores >= 1
    assert h.ram_total_mb > 256 and "CPUExecutionProvider" in h.providers
    assert not (set(h.providers) & BLOCKED_PROVIDERS)           # never Azure: would leave the device


def test_automatic_leaves_headroom_and_scales():
    assert cfg("automatic", hw(2, 4)).intra_op_threads == 2
    assert cfg("automatic", hw(4, 8)).intra_op_threads == 3
    assert cfg("automatic", hw(16, 32)).intra_op_threads == 8          # capped
    assert cfg("automatic", hw(1, 1)).intra_op_threads == 1


def test_automatic_prefers_measured_benchmark():
    c = cfg("automatic", hw(8, 16), benchmark_threads=2)
    assert c.intra_op_threads == 2 and "measured" in c.reason.lower()


def test_low_ram_switches_on_memory_saving():
    c = cfg("automatic", hw(4, 8, ram=2048))
    assert c.memory_arena is False and c.unload_after_idle_s


def test_profiles_behave_differently():
    h = hw(8, 16)
    fast, bal, hq, low = (cfg(p, h) for p in ("fastest", "balanced", "high_quality", "low_memory"))
    assert fast.intra_op_threads == 8 and bal.intra_op_threads == 4
    assert low.intra_op_threads <= 2 and low.memory_arena is False and low.unload_after_idle_s == 30
    assert hq.max_chunk_chars > bal.max_chunk_chars > low.max_chunk_chars
    assert all(c.inter_op_threads == 1 for c in (fast, bal, hq, low))


def test_custom_threads_clamped_to_machine():
    assert cfg("custom", hw(2, 4), custom_threads=64).intra_op_threads == 4
    assert cfg("custom", hw(2, 4), custom_threads=3).intra_op_threads == 3


def test_acceleration_only_when_available_and_requested():
    assert cfg("automatic", hw(4, 8), use_acceleration=True).use_acceleration is False
    assert cfg("automatic", hw(4, 8, accel=("DmlExecutionProvider",)), use_acceleration=True).use_acceleration
    assert cfg("automatic", hw(4, 8, accel=("DmlExecutionProvider",))).use_acceleration is False


def test_all_profiles_described():
    assert {p.id for p in PROFILES} == {"automatic", "fastest", "balanced", "high_quality", "low_memory", "custom"}
    assert all(len(p.description) > 20 for p in PROFILES)


def test_engine_reload_key_ignores_chunking():
    a = RuntimeConfig(intra_op_threads=2, max_chunk_chars=300)
    b = RuntimeConfig(intra_op_threads=2, max_chunk_chars=800)
    assert a.engine_key() == b.engine_key()
    assert a.engine_key() != RuntimeConfig(intra_op_threads=3).engine_key()


def test_system_endpoint(api):
    s = api.get("/api/system").json()
    assert s["network"] == {"bind_host": "127.0.0.1", "port": 8765, "internet_required": False}
    assert s["hardware"]["logical_cores"] >= 1 and len(s["profiles"]) == 6
    assert "ffmpeg" in s and s["engines"][0]["id"] == "kokoro"


@needs_model
def test_session_options_really_applied(api):
    from backend.engines.base import RuntimeConfig
    eng = api.app.state.ctx.engines.get("kokoro")
    eng.load(RuntimeConfig(intra_op_threads=1, memory_arena=False))
    so = eng._kokoro.sess.get_session_options()
    assert so.intra_op_num_threads == 1 and so.inter_op_num_threads == 1
    assert so.enable_cpu_mem_arena is False
    assert eng.status().provider == "CPUExecutionProvider"


@needs_model
def test_diagnostics_record_measured_values(api):
    api.wait_job(api.post("/api/jobs", {"text": "Diagnostics sample.", "export": {"format": "wav"}}).json()["id"])
    d = api.get("/api/diagnostics").json()
    assert d["recent"] and d["recent"][0]["rtf"] > 0
    assert d["summary"][0]["runs"] >= 1


@needs_model
def test_benchmark_runs_and_persists_recommendation(api):
    r = api.post("/api/benchmark")
    assert r.status_code == 200
    b = r.json()
    assert b["recommended_threads"] >= 1 and all(x["rtf"] > 0 for x in b["results"] if x["ok"])
    assert api.get("/api/settings").json()["benchmark_threads"] == b["recommended_threads"]


@needs_model
def test_model_integrity_verification(api):
    r = api.post("/api/models/verify").json()
    assert r["all_ok"] is True and len(r["results"]) == 2
