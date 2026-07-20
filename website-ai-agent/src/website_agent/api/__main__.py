"""Run the API server: ``python -m website_agent.api``.

Design rationale: a tiny launcher so the server starts without a separate script. Host and
port come from environment (WA_API_HOST, WA_API_PORT) with sensible local defaults; the app
itself is built from the standard settings, so the same configuration drives CLI and server.
"""

from __future__ import annotations

import os

import uvicorn

from website_agent.api.app import create_app


def main() -> None:
    """Start uvicorn serving the FastAPI app."""
    host = os.environ.get("WA_API_HOST", "127.0.0.1")
    port = int(os.environ.get("WA_API_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
