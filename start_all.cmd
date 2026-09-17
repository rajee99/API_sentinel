@echo off
setlocal
title API Sentinel - Start All
color 0F

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "API_URL=http://127.0.0.1:8000"
set "DASHBOARD_URL=http://127.0.0.1:8001"

echo.
echo  =====================================================
echo   API Sentinel - Start All Services
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

echo [1/4] Starting Demo API on port 8000...
start "API Sentinel - Demo API" "%ComSpec%" /k call "%~dp0start_api.cmd"

echo Waiting for Demo API...
set "READY="
for /l %%N in (1,1,15) do (
    if not defined READY (
        "%PYTHON%" -c "import urllib.request; urllib.request.urlopen('%API_URL%/docs', timeout=1).read()" >nul 2>&1
        if not errorlevel 1 set "READY=1"
        if not defined READY timeout /t 1 /nobreak >nul
    )
)

if not defined READY (
    echo [ERROR] Demo API did not start within 15 seconds.
    echo Check the Demo API window for the error.
    pause
    exit /b 1
)
echo       Demo API is ready.

echo.
echo [2/4] Starting Dashboard on port 8001...
start "API Sentinel - Dashboard" "%ComSpec%" /k call "%~dp0start_dashboard.cmd"

echo Waiting for Dashboard...
set "READY="
for /l %%N in (1,1,15) do (
    if not defined READY (
        "%PYTHON%" -c "import urllib.request; urllib.request.urlopen('%DASHBOARD_URL%', timeout=1).read()" >nul 2>&1
        if not errorlevel 1 set "READY=1"
        if not defined READY timeout /t 1 /nobreak >nul
    )
)

if not defined READY (
    echo [ERROR] Dashboard did not start within 15 seconds.
    echo Check the Dashboard window for the error.
    pause
    exit /b 1
)
echo       Dashboard is ready.

echo.
echo [3/4] Creating validation issues...
set "PYTHONIOENCODING=utf-8"
"%PYTHON%" "%~dp0push_to_dashboard.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Validation run failed.
    echo Check the output above.
    pause
    exit /b 1
)

echo.
echo [4/4] Opening dashboard and Swagger UI...
start "" "%DASHBOARD_URL%"
start "" "%API_URL%/docs"

echo.
echo  =====================================================
echo   API Sentinel is running.
echo.
echo   Demo API   : %API_URL%
echo   Swagger UI : %API_URL%/docs
echo   Dashboard  : %DASHBOARD_URL%
echo.
echo   Create issues again with:
echo       push_issues.cmd
echo  =====================================================
echo.
pause
