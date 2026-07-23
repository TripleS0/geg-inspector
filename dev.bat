@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8765"
if defined GEG_INSPECTOR_HOST set "BACKEND_HOST=%GEG_INSPECTOR_HOST%"
if defined GEG_INSPECTOR_BACKEND_PORT set "BACKEND_PORT=%GEG_INSPECTOR_BACKEND_PORT%"

set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%~dp0frontend\node_modules\" (
  echo Installing frontend dependencies...
  pushd "%~dp0frontend"
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
  popd
)

echo Starting backend: http://%BACKEND_HOST%:%BACKEND_PORT%
set "PYTHONPATH=%~dp0backend;%PYTHONPATH%"
start "DataFusionX-Backend" /min cmd /c ""%PYTHON%" -m uvicorn backend.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload --reload-dir "%~dp0backend""

echo Starting frontend: http://127.0.0.1:5173
start "DataFusionX-Frontend" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Dev servers started in separate windows.
echo   Frontend  http://127.0.0.1:5173
echo   Backend   http://%BACKEND_HOST%:%BACKEND_PORT%/api/health
echo   Default admin  admin / admin123
echo.
echo Close those windows or run taskkill to stop them.
pause
