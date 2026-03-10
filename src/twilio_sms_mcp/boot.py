"""Launcher for the webhook HTTP server and the MCP stdio server."""

from __future__ import annotations

import logging
import threading

import uvicorn

from . import __version__
from .config import get_settings, setup_logging
from .store import init_db
from .webhook import app

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Twilio SMS MCP server v%s starting", __version__)
    init_db()

    webhook_server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.webhook_port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    )
    threading.Thread(target=webhook_server.run, name="twilio-webhook", daemon=True).start()
    logger.info("Webhook server listening on 0.0.0.0:%d", settings.webhook_port)

    from .server import main as run_mcp_server

    run_mcp_server()


if __name__ == "__main__":
    main()
