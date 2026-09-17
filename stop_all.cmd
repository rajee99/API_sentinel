@echo off
setlocal
title API Sentinel - Stop All Services
color 0C

echo.
echo  =====================================================
echo   API Sentinel - Stopping All Services (Ports 8000 & 8001)
echo  =====================================================
echo.

powershell -NoProfile -Command ^
    "$ports = @(8000, 8001); " ^
    "$found = $false; " ^
    "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | ForEach-Object { " ^
    "    $procId = $_.OwningProcess; " ^
    "    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue; " ^
    "    Write-Host ('[STOPPING] Port ' + $_.LocalPort + ' (PID ' + $procId + ' - ' + $proc.Name + ')'); " ^
    "    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue; " ^
    "    $found = $true; " ^
    "}; " ^
    "if (-not $found) { Write-Host 'No running API Sentinel services were found on ports 8000 or 8001.' -ForegroundColor Yellow } else { Write-Host 'All API Sentinel services stopped successfully.' -ForegroundColor Green }"

echo.
echo Done.
timeout /t 3 >nul
