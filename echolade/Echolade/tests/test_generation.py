"""End-to-end generation with the real Kokoro model (skipped if not installed)."""
import time

import soundfile as sf

from tests.conftest import needs_model

pytestmark = needs_model

TEXT = "Hello from Echolade. This is the first sentence.\n\nThis is a second paragraph of speech."


def _job(text=TEXT, **over):
    body = {"text": text, "name": "Test Run", "delivery": {"voice": "af_heart", "speed": 1.0},
            "export": {"format": "wav"}}
    body.update(over)
    return body


def test_voices_discovered(api):
    data = api.get("/api/voices").json()
    ids = {v["id"] for v in data["voices"]}
    assert {"af_heart", "bf_emma", "am_adam", "ef_dora"} <= ids
    assert len(data["voices"]) >= 50
    assert {l["code"] for l in data["languages"]} >= {"en-us", "en-gb", "es", "fr-fr"}


def test_empty_and_invalid_input_rejected(api):
    assert api.post("/api/jobs", _job(text="   \n  ")).status_code == 400
    assert api.post("/api/jobs", _job(text="")).status_code == 422
    r = api.post("/api/jobs", _job(delivery={"voice": "zz_nobody"}))
    assert r.status_code == 400 and "voice" in r.json()["detail"].lower()
    assert api.post("/api/jobs", _job(engine="nope")).status_code == 400
    assert api.post("/api/jobs", _job(export={"format": "exe"})).status_code == 422


def test_generate_wav_end_to_end(api):
    r = api.post("/api/jobs", _job())
    assert r.status_code == 202
    job = api.wait_job(r.json()["id"])
    assert job["status"] == "done", job
    res = job["result"]
    assert res["format"] == "wav" and res["status"] == "complete"
    assert job["progress"]["done"] == job["progress"]["total"] == 2   # two paragraphs
    m = job["metrics"]
    assert m["rtf"] and m["first_audio_s"] and m["audio_s"] > 2 and m["peak_rss_mb"]

    # the history entry is real, downloadable and a valid WAV
    dl = api.get(f"/api/history/{res['id']}/download")
    assert dl.status_code == 200 and dl.content[:4] == b"RIFF"
    assert "attachment" in dl.headers["content-disposition"]
    out = api.app.state.ctx.paths.outputs / res["file"]
    info = sf.info(str(out))
    assert info.samplerate == 24000 and info.channels == 1
    assert abs(info.duration - res["duration_s"]) < 0.05
    data, _ = sf.read(str(out))
    assert abs(data).max() > 0.05 and abs(data).max() <= 0.99      # audible, not clipped
    # paragraph pause (700ms) really is in the file: duration > sum of speech segments
    assert info.duration > m["audio_s"] + 0.5
    # temp chunks are cleaned up after a successful export
    assert not (api.app.state.ctx.paths.job_cache / job["id"]).exists()
    # served inline for the player, with Range support
    part = api.get(f"/api/history/{res['id']}/audio", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100


def test_progressive_segments_available_while_running(api):
    text = " ".join(f"Sentence number {i} is here." for i in range(60))
    r = api.post("/api/jobs", _job(text=text))
    jid = r.json()["id"]
    seen = None
    end = time.time() + 120
    while time.time() < end:
        j = api.get(f"/api/jobs/{jid}").json()
        if j["progress"]["done"] >= 1 and j["status"] == "running":
            seen = j
            seg = api.get(f"/api/jobs/{jid}/segments/0")
            assert seg.status_code == 200 and seg.content[:4] == b"RIFF"
            break
        if j["status"] != "queued" and j["status"] != "running":
            break
        time.sleep(0.1)
    api.post(f"/api/jobs/{jid}/cancel")
    api.wait_job(jid)
    assert seen is not None, "never observed a finished segment during generation"
    assert seen["metrics"]["first_audio_s"] is not None


def test_cancel_keeps_finished_segments_and_can_export_them(api):
    text = "\n\n".join(f"This is paragraph number {i}, with a little speech in it." for i in range(30))
    jid = api.post("/api/jobs", _job(text=text)).json()["id"]
    end = time.time() + 120
    while time.time() < end:
        if api.get(f"/api/jobs/{jid}").json()["progress"]["done"] >= 2:
            break
        time.sleep(0.1)
    assert api.post(f"/api/jobs/{jid}/cancel").status_code == 200
    j = api.wait_job(jid)
    assert j["status"] == "cancelled"
    done = j["progress"]["done"]
    assert 2 <= done < 30
    assert j["can_finalize"] and j["can_retry"]
    # export what finished: real file, flagged as partial
    assert api.post(f"/api/jobs/{jid}/finalize").status_code == 200
    j = api.wait_job(jid)
    assert j["status"] == "partial" and j["result"]["status"] == "partial"
    assert len(j["result"]["missing_segments"]) == 30 - done
    assert sf.info(str(api.app.state.ctx.paths.outputs / j["result"]["file"])).duration > 3


def test_failed_segment_is_isolated_and_retryable(api, monkeypatch):
    engine = api.app.state.ctx.engines.get("kokoro")
    real = engine.synthesize
    calls = {"n": 0}

    def flaky(text, voice, speed):
        calls["n"] += 1
        if "FAILME" in text and calls["n"] < 50 and not getattr(flaky, "healed", False):
            from backend.engines.base import EngineError
            raise EngineError("This text segment could not be converted to speech.")
        return real(text, voice, speed)

    monkeypatch.setattr(engine, "synthesize", flaky)
    text = "Good first paragraph here.\n\nFAILME paragraph two.\n\nGood third paragraph here."
    jid = api.post("/api/jobs", _job(text=text)).json()["id"]
    j = api.wait_job(jid)
    assert j["status"] == "partial"
    st = [c["status"] for c in j["chunks"]]
    assert st == ["done", "failed", "done"]            # others unaffected
    assert j["can_retry"] and not j["result"]           # nothing exported until user decides
    flaky.healed = True
    assert api.post(f"/api/jobs/{jid}/retry").status_code == 200
    j = api.wait_job(jid)
    assert j["status"] == "done" and j["result"]["status"] == "complete"
    assert j["progress"]["done"] == 3


def test_model_is_loaded_once_and_reused(api):
    ctx = api.app.state.ctx
    engine = ctx.engines.get("kokoro")
    before = engine.status().load_seconds
    for _ in range(2):
        j = api.wait_job(api.post("/api/jobs", _job(text="Quick reuse check.")).json()["id"])
        assert j["status"] == "done"
        assert j["metrics"]["init_s"] is None          # no reload on later jobs
    assert engine.status().load_seconds == before and engine.is_loaded


def test_voice_preview_is_local_and_cached(api):
    r = api.post("/api/voices/kokoro/bf_emma/preview")
    assert r.status_code == 200
    url = r.json()["url"]
    a = api.get(url)
    assert a.status_code == 200 and a.content[:4] == b"RIFF"
    assert api.post("/api/voices/kokoro/zz_nope/preview").status_code in (400, 404)
    t0 = time.time()
    api.post("/api/voices/kokoro/bf_emma/preview")
    assert time.time() - t0 < 0.5                       # served from cache


def test_history_rename_delete(api):
    jid = api.post("/api/jobs", _job(text="History test line.", name="History Test")).json()["id"]
    res = api.wait_job(jid)["result"]
    path = api.app.state.ctx.paths.outputs / res["file"]
    assert path.is_file()
    assert api.patch(f"/api/history/{res['id']}", {"name": "Renamed ✓"}).json()["name"] == "Renamed ✓"
    dl = api.get(f"/api/history/{res['id']}/download")
    assert "Renamed" in dl.headers["content-disposition"] or "filename*" in dl.headers["content-disposition"]
    assert api.delete(f"/api/history/{res['id']}").status_code == 200
    assert not path.exists()
    assert api.get(f"/api/history/{res['id']}/download").status_code == 404


def test_name_collision_never_overwrites(api):
    ids = [api.post("/api/jobs", _job(text="Collision.", name="same name")).json()["id"] for _ in range(2)]
    files = [api.wait_job(i)["result"]["file"] for i in ids]
    assert files[0] != files[1]
    assert all((api.app.state.ctx.paths.outputs / f).is_file() for f in files)


def test_hostile_name_stays_inside_outputs(api):
    jid = api.post("/api/jobs", _job(text="Path test.", name="../../../tmp/pwned")).json()["id"]
    res = api.wait_job(jid)["result"]
    out = api.app.state.ctx.paths.outputs
    assert (out / res["file"]).is_file() and (out / res["file"]).resolve().parent == out.resolve()


def test_text_too_long_is_refused_cleanly(api):
    r = api.post("/api/jobs", _job(text=("word " * 30000)))
    assert r.status_code in (400, 413, 422) and "Traceback" not in r.text
