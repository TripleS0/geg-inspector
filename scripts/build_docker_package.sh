#!/usr/bin/env bash
# Build a zip package for end-user Docker deployment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/dist"
ZIP_NAME="geg-inspector-docker.zip"
STAGING="$OUT_DIR/geg-inspector-docker"

rm -rf "$STAGING"
mkdir -p "$STAGING" "$OUT_DIR"

copy_item() {
  local src="$1"
  local dest="$2"
  if [[ -e "$ROOT/$src" ]]; then
    mkdir -p "$(dirname "$STAGING/$dest")"
    cp -R "$ROOT/$src" "$STAGING/$dest"
  fi
}

for item in \
  README-DOCKER.md \
  docker-compose.yml \
  docker-compose.mirror.cn.yml \
  start.bat stop.bat start-mirror.bat rebuild.bat rebuild-mirror.bat \
  start.sh stop.sh start-mirror.sh \
  requirements.txt \
  .dockerignore \
  backend \
  frontend \
  mock-data; do
  copy_item "$item" "$item"
done

# Strip dev artefacts from the package
rm -rf \
  "$STAGING/frontend/node_modules" \
  "$STAGING/frontend/dist" \
  "$STAGING/backend/tests" \
  "$STAGING/backend/__pycache__" \
  "$STAGING/backend/app/__pycache__"

mkdir -p "$STAGING/data"

# Windows cmd.exe requires CRLF in .bat files
python3 - <<'PY'
from pathlib import Path
staging = Path("$STAGING")
for name in ("start.bat", "stop.bat", "start-mirror.bat", "rebuild.bat", "rebuild-mirror.bat"):
    path = staging / name
    if path.exists():
        text = path.read_text(encoding="utf-8")
        path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
PY

(
  cd "$OUT_DIR"
  rm -f "$ZIP_NAME"
  zip -r "$ZIP_NAME" "geg-inspector-docker"
)

echo "交付包已生成: $OUT_DIR/$ZIP_NAME"
echo "用户解压后双击 start-mirror.bat（国内）或 start.bat 即可启动。"
