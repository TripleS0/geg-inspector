@echo off
echo 正在启动 DataFusionX（使用国内镜像加速）...

docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
if errorlevel 1 (
    echo 启动失败。若仍超时，请配置 Docker Desktop 镜像加速，详见 README-DOCKER.md
    pause
    exit /b 1
)

echo 系统已启动
start http://localhost:8080

pause
