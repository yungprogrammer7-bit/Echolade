from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
HAVE_MODEL = (MODELS / "kokoro-v1.0.onnx").is_file() and (MODELS / "voices-v1.0.bin").is_file()
needs_model = pytest.mark.skipif(not HAVE_MODEL, reason="Kokoro model files not downloaded")

PORT = 8765
HOST = f"127.0.0.1:{PORT}"


class Api:
    """TestClient wrapper that behaves like the real front-end (token + same origin)."""

    def __init__(self, app):
        self.app = app
        self.token = app.state.ctx.security.token
        self.c = TestClient(app, base_url=f"http://{HOST}")

    def hdr(self, token=True, origin=f"http://{HOST}"):
        h = {}
        if token:
            h["X-Echolade-Token"] = self.token
        if origin:
            h["Origin"] = origin
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        kw.setdefault("headers", self.hdr())
        return self.c.post(url, json=json, **kw)

    def patch(self, url, json=None, **kw):
        kw.setdefault("headers", self.hdr())
        return self.c.patch(url, json=json, **kw)

    def delete(self, url, **kw):
        kw.setdefault("headers", self.hdr())
        return self.c.delete(url, **kw)

    def wait_job(self, job_id, timeout=180):
        end = time.time() + timeout
        while time.time() < end:
            j = self.get(f"/api/jobs/{job_id}").json()
            if j["status"] in ("done", "partial", "failed", "cancelled"):
                return j
            time.sleep(0.2)
        raise TimeoutError("job did not finish")


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    home = tmp_path_factory.mktemp("echolade_home")
    app = create_app(home=home, models=MODELS, port=PORT, lower_priority=False)
    with TestClient(app):  # runs lifespan (start/stop worker cleanly)
        yield Api(app)
