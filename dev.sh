#!/usr/bin/env bash
# 本地开发：同时启动后端 (8765) 与前端 (5173)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BACKEND_HOST="${GEG_INSPECTOR_HOST:-127.0.0.1}"
BACKEND_PORT="${GEG_INSPECTOR_BACKEND_PORT:-8765}"
FRONTEND_DIR="$ROOT/frontend"

resolve_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

PYTHON="$(resolve_python)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo "正在停止前后端..."
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  # 清理可能残留的子进程（uvicorn reload / vite）
  pkill -P $$ 2>/dev/null || true
  echo "已停止"
}

trap cleanup EXIT INT TERM

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "前端依赖未安装，正在执行 npm install..."
  (cd "$FRONTEND_DIR" && npm install)
fi

echo "启动后端: http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Python: $PYTHON"
PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m uvicorn backend.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --reload \
  --reload-dir "$ROOT/backend" &
BACKEND_PID=$!

echo "启动前端: http://127.0.0.1:5173"
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "开发服务已启动（Ctrl+C 同时关闭）"
echo "  前端  http://127.0.0.1:5173"
echo "  后端  http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
echo "  默认管理员  admin / admin123"
echo ""

# 兼容 macOS Bash 3.2（无 wait -n）：轮询任一子进程退出
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
