"""Local-server hardening (spec 13.1, 13.4).

* Host-header allow-list  -> blocks DNS-rebinding attacks.
* Origin check + per-launch session token on every state-changing request
  -> blocks cross-site request forgery from web pages open in the same browser.
* Request-size cap, strict CSP and other security headers on every response.
* No CORS headers are ever sent, so other origins cannot read responses.
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import LIMITS

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOKEN_HEADER = "x-echolade-token"

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "media-src 'self' blob:",
    "connect-src 'self'",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityConfig:
    def __init__(self, port: int, extra_hosts: set[str] | None = None):
        self.port = port
        self.token = secrets.token_urlsafe(32)
        hosts = {"127.0.0.1", "localhost", "[::1]"}
        self.allowed_hosts = hosts | {f"{h}:{port}" for h in hosts} | (extra_hosts or set())
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}

    def token_ok(self, supplied: str | None) -> bool:
        return bool(supplied) and hmac.compare_digest(supplied.encode(), self.token.encode())


def _deny(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status, headers=dict(SECURITY_HEADERS))


def install_security(app, sec: SecurityConfig) -> None:
    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").lower()
        if host not in sec.allowed_hosts:
            return _deny(403, "Request rejected: unexpected host.")

        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin.lower() not in sec.allowed_origins:
                return _deny(403, "Request rejected: cross-origin request blocked.")
            if request.url.path.startswith("/api/") and not sec.token_ok(
                    request.headers.get(TOKEN_HEADER)):
                return _deny(403, "Request rejected: missing or invalid session token.")

            length = request.headers.get("content-length")
            if length is None:
                if "chunked" in request.headers.get("transfer-encoding", "").lower():
                    return _deny(411, "Content-Length is required.")
            else:
                try:
                    if int(length) > LIMITS.max_body_bytes:
                        return _deny(413, "Request is too large.")
                except ValueError:
                    return _deny(400, "Malformed Content-Length.")

        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response
