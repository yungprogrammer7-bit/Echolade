"""Real encoding checks: files must decode, have the right length and parameters."""
import numpy as np
import pytest
import soundfile as sf

from backend.audio import conversion
from tests.conftest import needs_model

pytestmark = pytest.mark.skipif(not conversion.ffmpeg_available(), reason="ffmpeg not available")


@pytest.fixture()
def master(tmp_path):
    sr = 24000
    t = np.arange(sr * 2) / sr
    tone = (0.4 * np.sin(2 * np.pi * 440 * t)).astype("float32")
    p = tmp_path / "master.wav"
    sf.write(str(p), tone, sr, subtype="FLOAT")
    return p


def _export(master, tmp_path, fmt, **kw):
    dest = tmp_path / f"out.{fmt}"
    opts = dict(fmt=fmt, native_rate=24000, sample_rate=24000, channels=1, mp3_bitrate=192, title="T")
    opts.update(kw)
    conversion.export_audio(master, dest, **opts)
    return dest


def test_wav_plain(master, tmp_path):
    d = _export(master, tmp_path, "wav")
    info = sf.info(str(d))
    assert (info.samplerate, info.channels, info.subtype) == (24000, 1, "PCM_16")
    assert conversion.validate_output(d, 2.0, "wav") == pytest.approx(2.0, abs=0.05)
    assert not (tmp_path / "out.wav.part").exists()


@pytest.mark.parametrize("sr,ch", [(44100, 1), (48000, 2)])
def test_wav_resampled_stereo(master, tmp_path, sr, ch):
    d = _export(master, tmp_path, "wav", sample_rate=sr, channels=ch)
    info = sf.info(str(d))
    assert (info.samplerate, info.channels) == (sr, ch)
    conversion.validate_output(d, 2.0, "wav")


@pytest.mark.parametrize("bitrate", [96, 192, 256])
def test_mp3_valid_and_bitrate_scales(master, tmp_path, bitrate):
    d = _export(master, tmp_path, "mp3", mp3_bitrate=bitrate)
    assert d.read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    assert conversion.validate_output(d, 2.0, "mp3") == pytest.approx(2.0, abs=0.15)
    # ~bitrate/8 bytes per second, 2 s of audio (allow header/ID3 overhead)
    assert d.stat().st_size == pytest.approx(bitrate * 1000 / 8 * 2, rel=0.35)


def test_corrupt_file_fails_validation(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"this is not audio" * 20)
    with pytest.raises(conversion.ExportError):
        conversion.validate_output(bad, 2.0, "mp3")
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(conversion.ExportError):
        conversion.validate_output(empty, 2.0, "wav")


def test_unique_path(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    assert conversion.unique_path(tmp_path, "a", "mp3").name == "a-2.mp3"


@needs_model
def test_mp3_through_api(api):
    body = {"text": "An MP3 export check.", "name": "mp3 check",
            "export": {"format": "mp3", "mp3_bitrate": 128}}
    j = api.wait_job(api.post("/api/jobs", body).json()["id"])
    assert j["status"] == "done", j
    res = j["result"]
    path = api.app.state.ctx.paths.outputs / res["file"]
    assert path.suffix == ".mp3"
    assert conversion.probe_duration(path) == pytest.approx(res["duration_s"], abs=0.1)
    dl = api.get(f"/api/history/{res['id']}/download")
    assert dl.headers["content-type"] == "audio/mpeg"


@needs_model
def test_volume_never_clips(api):
    body = {"text": "Loud volume test sentence.", "name": "loud",
            "delivery": {"voice": "af_heart", "volume_db": 6.0}, "export": {"format": "wav"}}
    j = api.wait_job(api.post("/api/jobs", body).json()["id"])
    data, _ = sf.read(str(api.app.state.ctx.paths.outputs / j["result"]["file"]))
    assert abs(data).max() <= 0.99
