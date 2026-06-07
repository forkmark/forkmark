@echo off
setlocal
title Forkmark — Stop

set COMPOSE_FILE=docker-compose.simple.yml
set HERE=%~dp0
cd /d "%HERE%"

echo.
echo   Stopping Forkmark...
echo.

:: Compose v2 first, fall back to v1
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    docker compose -f %COMPOSE_FILE% down
) else (
    where docker-compose >nul 2>&1
    if %errorlevel% equ 0 (
        docker-compose -f %COMPOSE_FILE% down
    ) else (
        echo   Docker Compose not found.
        echo   If Forkmark is running in a terminal window, press Ctrl+C there.
        goto :end
    )
)

if %errorlevel% equ 0 (
    echo.
    echo   Forkmark stopped. Your data is preserved.
    echo   Run start.bat to restart.
) else (
    echo.
    echo   Something went wrong. Is Docker Desktop running?
)

:end
echo.
pause
