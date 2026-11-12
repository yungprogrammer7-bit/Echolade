"""Application factory."""
from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import generation, routes, settings, voices
from .audio.conversion import ExportError
from .audio.generator import JobManager
from .config import APP_NAME, APP_VERSION, DEFAULT_PORT, Paths, default_paths
from .context import AppContext
from .engines.base import EngineError
from .engines.engine_manager import EngineManager
from .errors import UserError
from .hardware_detection import HardwareInfo, detect_hardware, lower_process_priority
from .security import SECURITY_HEADERS, SecurityConfig, install_security
from .services.history_service import HistoryService
from .services.metrics_service import MetricsService
from .services.settings_service import SettingsService
from .services.storage_service import StorageService
from .services.voice_service import VoiceService

log = logging.getLogger("echolade")


def _setup_logging(paths: Paths) -> None:
    root = logging.getLogger("echolade")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    try:
        handler = logging.handlers.RotatingFileHandler(
            paths.logs / "echolade.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    except OSError:
        pass  # logging must never stop the app from starting


def _json(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status, headers=dict(SECURITY_HEADERS))


def create_app(home: Path | None = None, models: Path | None = None, port: int = DEFAULT_PORT,
               hardware: HardwareInfo | None = None, extra_hosts: set[str] | None = None,
               lower_priority: bool = True) -> FastAPI:
    paths = default_paths(home, models)
    paths.ensure()
    _setup_logging(paths)
    hw = hardware or detect_hardware(paths.outputs)
    if lower_priority:
        lower_process_priority()

    security = SecurityConfig(port, extra_hosts)
    settings_svc = SettingsService(paths)
    history = HistoryService(paths)
    metrics = MetricsService(paths)
    engines = EngineManager(paths)

    holder: dict = {}
    get_runtime = lambda: holder["ctx"].runtime()  # noqa: E731
    voices_svc = VoiceService(paths, engines, get_runtime)
    jobs = JobManager(paths, engines, history, metrics, get_runtime)
    ctx = AppContext(paths, security, hw, settings_svc, history, metrics, engines, voices_svc,
                     StorageService(paths), jobs)
    holder["ctx"] = ctx

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings_svc.get().warmup:
            jobs.warmup()
        yield
        jobs.shutdown()

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    install_security(app, security)

    @app.exception_handler(UserError)
    async def _user(_: Request, exc: UserError):
        return _json(exc.status, exc.message)

    @app.exception_handler(EngineError)
    async def _engine(_: Request, exc: EngineError):
        return _json(503, str(exc))

    @app.exception_handler(ExportError)
    async def _export(_: Request, exc: ExportError):
        return _json(500, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        # Never echo the submitted values back (they may be private text).
        parts = []
        for err in exc.errors()[:3]:
            field = ".".join(str(p) for p in err.get("loc", ())[1:]) or "request"
            parts.append(f"{field}: {err.get('msg', 'invalid')}")
        return _json(422, "Invalid input — " + "; ".join(parts))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return _json(500, "Something went wrong on this computer. Your text was not lost; try again.")

    for r in (routes.router, settings.router, voices.router, generation.router):
        app.include_router(r)

    index_html = (paths.frontend / "index.html").read_text(encoding="utf-8") \
        if (paths.frontend / "index.html").is_file() else "<h1>Echolade frontend missing</h1>"

    @app.get("/", response_class=HTMLResponse)
    def index():
        html = index_html.replace("__ECHOLADE_TOKEN__", security.token)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(paths.frontend / "assets" / "favicon.svg", media_type="image/svg+xml")

    for sub in ("css", "js", "assets"):
        d = paths.frontend / sub
        if d.is_dir():
            app.mount(f"/{sub}", StaticFiles(directory=d), name=sub)
    return app
