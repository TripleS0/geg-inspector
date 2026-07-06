#!/usr/bin/env bash
set -euo pipefail

echo "正在启动 DataFusionX..."

if docker compose up -d --no-build; then
  :
else
  echo "未找到镜像，开始首次构建..."
  docker compose up -d --build
fi

echo "系统已启动"

if command -v open >/dev/null 2>&1; then
  open "http://localhost:8080"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8080"
else
  echo "请在浏览器打开: http://localhost:8080"
fi
