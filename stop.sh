#!/usr/bin/env bash
set -euo pipefail

echo "正在关闭 DataFusionX..."

docker compose down

echo "系统已关闭"
