@echo off
echo Rebuilding DataFusionX...

docker compose up -d --build
if errorlevel 1 (
    echo Rebuild failed. Please confirm Docker Desktop is running.
    pause
    exit /b 1
)

echo Rebuild complete. System started.
start http://localhost:8080

pause
