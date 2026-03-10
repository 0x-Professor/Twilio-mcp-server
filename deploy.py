"""Prefect Cloud / FastMCP Cloud deployment entry point.

Deploy with:
    uvx prefect-cloud deploy deploy.py:run_server \
        --from 0x-Professor/Twilio-mcp-server \
        --name twilio-sms-mcp \
        --with "fastmcp>=3.0.0" \
        --with "twilio>=9.0.0" \
        --with "pydantic-settings>=2.0.0" \
        --with "python-dotenv>=1.0.0" \
        --with "httpx>=0.27.0" \
        --with "uvicorn>=0.29.0" \
        --with "fastapi>=0.110.0"
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_server() -> None:
    """Start the Twilio SMS MCP server with HTTP transport for cloud deployment."""
    # Install the package from the cloned repo so twilio_sms_mcp is importable
    repo_root = Path(__file__).resolve().parent
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", str(repo_root)],
    )

    # Default to HTTP transport in cloud environments (recommended over SSE)
    os.environ.setdefault("MCP_TRANSPORT", "http")
    os.environ.setdefault("MCP_HOST", "0.0.0.0")
    os.environ.setdefault("MCP_PORT", "8000")

    from twilio_sms_mcp.boot import main

    main()


if __name__ == "__main__":
    run_server()
