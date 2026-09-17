@echo off
setlocal
title API Sentinel - Dashboard (Port 8001)
color 0B

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

echo.
echo  =====================================================
echo   API Sentinel - Dashboard
echo   http://127.0.0.1:8001
echo  =====================================================
echo.

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment was not found:
    echo         %PYTHON%
    echo.
    echo Create it with:
    echo         py -m venv .venv
    echo         .venv\Scripts\python.exe -m pip install -e .
    echo.
    pause
    exit /b 1
)

echo Starting Dashboard...
echo Press Ctrl+C to stop.
echo.

"%PYTHON%" -m uvicorn dashboard.app:app --reload --host 127.0.0.1 --port 8001

echo.
echo Dashboard stopped.
pause
