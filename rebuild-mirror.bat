@echo off
echo Rebuilding DataFusionX with China mirror...

docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
if errorlevel 1 (
    echo Rebuild failed. See README-DOCKER.md for Docker mirror setup.
    pause
    exit /b 1
)

echo Rebuild complete. System started.
start http://localhost:8080

pause
