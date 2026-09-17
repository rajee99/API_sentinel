@echo off
setlocal
title API Sentinel - Demo API (Port 8000)
color 0A

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

echo.
echo  =====================================================
echo   API Sentinel - Demo API Server
echo   http://127.0.0.1:8000
echo   http://127.0.0.1:8000/docs  ^<-- Swagger UI
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

echo Starting Demo API...
echo Press Ctrl+C to stop.
echo.

"%PYTHON%" -m uvicorn example_app:app --reload --host 127.0.0.1 --port 8000

echo.
echo Demo API stopped.
pause
