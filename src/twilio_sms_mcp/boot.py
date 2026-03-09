"""Container-friendly launcher for the webhook and MCP servers."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys

from .config import get_settings
from .store import init_db


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    settings = get_settings()
    init_db()

    webhook_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "twilio_sms_mcp.webhook:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(settings.webhook_port),
            "--log-level",
            settings.log_level.lower(),
        ],
        env=os.environ.copy(),
    )
    atexit.register(_stop_process, webhook_process)

    def _raise_interrupt(_signum, _frame) -> None:
        raise KeyboardInterrupt

    for sig_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig_name):
            signal.signal(getattr(signal, sig_name), _raise_interrupt)

    try:
        from .server import main as run_mcp_server

        run_mcp_server()
    finally:
        _stop_process(webhook_process)
