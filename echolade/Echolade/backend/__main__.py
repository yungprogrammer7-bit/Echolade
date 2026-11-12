"""Start Echolade:  python -m backend"""
from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from .config import APP_NAME, APP_VERSION, BIND_HOST, DEFAULT_PORT
from .main import create_app


def _free_port(start: int) -> int:
    for port in range(start, start + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((BIND_HOST, port))
                return port
            except OSError:
                continue
    raise SystemExit("No free local port found between %d and %d." % (start, start + 24))


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{APP_NAME} local text-to-speech")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args()

    port = _free_port(args.port)
    app = create_app(port=port)
    url = f"http://{BIND_HOST}:{port}"
    print(f"\n  {APP_NAME} {APP_VERSION} is running at {url}")
    print("  Only this computer can reach it. Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(app, host=BIND_HOST, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
