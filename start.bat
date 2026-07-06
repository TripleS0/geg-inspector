@echo off
echo Starting DataFusionX...

docker compose up -d --no-build
if errorlevel 1 (
    echo Images not found. Building now ^(first run^)...
    docker compose up -d --build
    if errorlevel 1 (
        echo Startup failed. Please install and start Docker Desktop first.
        pause
        exit /b 1
    )
)

echo System started.
start http://localhost:8080

pause
