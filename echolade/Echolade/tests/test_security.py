import pytest

from tests.conftest import HOST

JOB = {"text": "Hello there.", "delivery": {"voice": "af_heart"}}


def test_index_has_token_and_headers(api):
    r = api.get("/")
    assert r.status_code == 200
    assert "content-security-policy" in r.headers and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_bad_host_rejected(api):
    r = api.get("/api/health", headers={"Host": "evil.example.com"})
    assert r.status_code == 403
    r = api.get("/api/health", headers={"Host": f"127.0.0.1.evil.com:8765"})
    assert r.status_code == 403
    assert api.get("/api/health").status_code == 200


def test_post_requires_token(api):
    r = api.post("/api/jobs", JOB, headers=api.hdr(token=False))
    assert r.status_code == 403
    r = api.post("/api/jobs", JOB, headers={**api.hdr(), "X-Echolade-Token": "wrong"})
    assert r.status_code == 403


def test_cross_origin_blocked_even_with_token(api):
    r = api.post("/api/jobs", JOB, headers=api.hdr(origin="http://evil.example.com"))
    assert r.status_code == 403
    r = api.patch("/api/settings", {"theme": "dark"}, headers=api.hdr(origin="null"))
    assert r.status_code == 403


def test_delete_requires_token(api):
    r = api.delete("/api/history/" + "0" * 32, headers=api.hdr(token=False))
    assert r.status_code == 403


def test_oversize_body_rejected(api):
    big = "a" * 1_200_000
    r = api.post("/api/jobs", {"text": big}, )
    assert r.status_code == 413


@pytest.mark.parametrize("bad", ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "x" * 40, "ZZ" * 16])
def test_ids_are_validated(api, bad):
    for url in (f"/api/history/{bad}/audio", f"/api/history/{bad}/download", f"/api/jobs/{bad}"):
        assert api.get(url).status_code in (404, 422)


@pytest.mark.parametrize("name", ["../secret.wav", "..\\secret.wav", "kokoro-af_heart.wav/../x", "a.wav"])
def test_preview_path_traversal(api, name):
    assert api.get(f"/api/previews/{name}").status_code == 404


def test_static_traversal_blocked(api):
    for p in ("/js/../../backend/main.py", "/css/..%2f..%2fbackend%2fmain.py", "/assets/../index.html"):
        r = api.get(p)
        assert "create_app" not in r.text


def test_validation_errors_do_not_echo_input(api):
    r = api.post("/api/jobs", {"text": "SECRET-TEXT-123", "delivery": {"voice": "../../x"}})
    assert r.status_code == 422
    assert "SECRET-TEXT-123" not in r.text and "Traceback" not in r.text


def test_settings_validation(api):
    assert api.patch("/api/settings", {"speed": 99}).status_code in (400, 422)
    assert api.patch("/api/settings", {"unknown_key": 1}).status_code == 422
    assert api.patch("/api/settings", {"favourites": ["../x"]}).status_code in (400, 422)
    assert api.patch("/api/settings", {"theme": "dark"}).status_code == 200
    assert api.get("/api/settings").json()["theme"] == "dark"
    api.patch("/api/settings", {"theme": "system"})


def test_filename_cannot_escape_outputs(api):
    """A hostile project name must never produce a path outside outputs/."""
    from backend.validation import safe_filename
    for n in ("../../../tmp/pwn", "..\\..\\windows\\system32\\x", "/etc/cron.d/x", "C:\\x\\y"):
        out = safe_filename(n)
        assert "/" not in out and "\\" not in out and ".." not in out and ":" not in out


def test_unknown_api_path_is_clean_404(api):
    r = api.get("/api/nope")
    assert r.status_code == 404 and "Traceback" not in r.text


def test_host_constant():
    assert HOST == "127.0.0.1:8765"
