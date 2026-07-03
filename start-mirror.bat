@echo off
echo Starting DataFusionX...

docker compose up -d --no-build
if errorlevel 1 (
    echo Images not found. Building with China mirror ^(first run or after update^)...
    docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
    if errorlevel 1 (
        echo Startup failed. See README-DOCKER.md for Docker mirror setup.
        pause
        exit /b 1
    )
)

echo System started.
start http://localhost:8080

pause
