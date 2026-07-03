#!/usr/bin/env bash
set -euo pipefail

echo "正在启动 DataFusionX..."

if docker compose up -d --no-build; then
  :
else
  echo "未找到镜像，使用国内镜像加速构建（首次运行或更新后）..."
  docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
fi

echo "系统已启动"

if command -v open >/dev/null 2>&1; then
  open "http://localhost:8080"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8080"
else
  echo "请在浏览器打开: http://localhost:8080"
fi
