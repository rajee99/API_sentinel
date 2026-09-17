@echo off
setlocal
title API Sentinel - Create Issues and Push to Dashboard
color 0E

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "API_URL=http://127.0.0.1:8000"
set "DASHBOARD_URL=http://127.0.0.1:8001"

echo.
echo  =====================================================
echo   API Sentinel - Create Issues ^& Push to Dashboard
echo  =====================================================
echo.

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment was not found:
    echo         %PYTHON%
    echo.
    pause
    exit /b 1
)

echo [1/3] Checking Demo API...
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('%API_URL%/docs', timeout=3).read()"
if errorlevel 1 (
    echo [ERROR] Demo API is not running on port 8000.
    echo.
    echo Start it first with:
    echo         start_api.cmd
    echo.
    pause
    exit /b 1
)
echo       Demo API is OK.

echo.
echo [2/3] Checking Dashboard...
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('%DASHBOARD_URL%', timeout=3).read()"
if errorlevel 1 (
    echo [ERROR] Dashboard is not running on port 8001.
    echo.
    echo Start it first with:
    echo         start_dashboard.cmd
    echo.
    pause
    exit /b 1
)
echo       Dashboard is OK.

echo.
echo [3/3] Running validation scenarios...
echo       This creates validation issues and pushes the report.
echo.

set "PYTHONIOENCODING=utf-8"
"%PYTHON%" "%~dp0push_to_dashboard.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Validation run failed.
    echo Check the messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo  =====================================================
echo   Done! Dashboard has been updated.
echo   http://127.0.0.1:8001
echo  =====================================================
echo.

start "" "%DASHBOARD_URL%"
pause
