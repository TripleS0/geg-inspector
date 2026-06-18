#!/usr/bin/env bash
set -euo pipefail

echo "正在启动 DataFusionX（使用国内镜像加速）..."

docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build

echo "系统已启动"

if command -v open >/dev/null 2>&1; then
  open "http://localhost:8080"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8080"
else
  echo "请在浏览器打开: http://localhost:8080"
fi
