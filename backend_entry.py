"""Entry point used by PyInstaller to build a single backend.exe.

It honours ``DATAFUSIONX_BACKEND_PORT`` and ``DATAFUSIONX_HOST`` environment
variables, defaulting to ``127.0.0.1:8765`` so that the desktop shell can
launch the backend on a free port.
"""

from __future__ import annotations

import os

import uvicorn

from backend.main import app


def main() -> int:
    host = os.environ.get("DATAFUSIONX_HOST", "127.0.0.1")
    port = int(os.environ.get("DATAFUSIONX_BACKEND_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
