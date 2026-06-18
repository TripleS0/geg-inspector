@echo off
echo 正在启动 DataFusionX...

docker compose up -d --build
if errorlevel 1 (
    echo 启动失败，请确认已安装 Docker Desktop 并已启动。
    pause
    exit /b 1
)

echo 系统已启动
start http://localhost:8080

pause
