"""Build a self-contained backend.exe for the offline desktop shell.

Usage:
    python scripts/build_backend.py

This wraps PyInstaller and writes the artefact to ``backend-dist/backend.exe``
so that Tauri can pick it up via the ``resources`` entry in
``src-tauri/tauri.conf.json``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DIST_DIR = ROOT / "backend-dist"
WORK_DIR = ROOT / "build"
SPEC_FILE = ROOT / "backend.spec"


def main() -> int:
    if shutil.which("pyinstaller") is None:
        print("[!] PyInstaller 未安装，请先执行: pip install pyinstaller")
        return 1
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--name",
        "backend",
        "--onefile",
        "--console",
        "--paths",
        str(ROOT),
        "--paths",
        str(BACKEND_DIR),
        "--add-data",
        f"backend/app/resources/sql/bootstrap_sqlite.sql{';' if sys.platform == 'win32' else ':'}app/resources/sql",
        "--add-data",
        f"backend/app/resources/sql/bootstrap_postgres.sql{';' if sys.platform == 'win32' else ':'}app/resources/sql",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR),
        "--specpath",
        str(ROOT),
        str(BACKEND_DIR / "entry.py"),
    ]
    print("[*] 调用 PyInstaller:")
    print("    " + " ".join(cmd))
    result = subprocess.call(cmd)
    if result != 0:
        return result
    print(f"[+] 构建完成，可执行文件位于：{DIST_DIR / ('backend.exe' if sys.platform == 'win32' else 'backend')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
