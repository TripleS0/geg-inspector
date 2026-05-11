"""Entry point used by PyInstaller to build a single backend.exe.

It honours ``DATAFUSIONX_BACKEND_PORT`` and ``DATAFUSIONX_HOST`` environment
variables, defaulting to ``127.0.0.1:8765`` so that the desktop shell can
launch the backend on a free port.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# PyInstaller：保证能解析顶层包 `backend`（与源码运行一致）。
_here = Path(__file__).resolve().parent
_roots = {_here.parent}
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):  # type: ignore[attr-defined]
    _roots.add(Path(getattr(sys, "_MEIPASS")))
for root in sorted(_roots, key=len):
    s = str(root)
    if s and s not in sys.path:
        sys.path.insert(0, s)

import uvicorn

from backend.main import app  # noqa: E402  # import after sys.path


def main() -> int:
    host = os.environ.get("DATAFUSIONX_HOST", "127.0.0.1")
    port = int(os.environ.get("DATAFUSIONX_BACKEND_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
