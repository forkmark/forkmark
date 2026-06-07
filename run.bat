@echo off
title Forkmark
color 0A

echo.
echo  ==============================
echo   Forkmark
echo  ==============================
echo.

:: Check Docker is available
where docker >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo ERROR: Docker not found.
    echo.
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo Then try again.
    echo.
    pause
    exit /b 1
)

:: Check Docker daemon is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo ERROR: Docker Desktop is not running.
    echo.
    echo Please open Docker Desktop and wait for it to start, then try again.
    echo.
    pause
    exit /b 1
)

echo Starting Forkmark...
echo (First run takes a few minutes to build — subsequent starts are instant.)
echo.

docker compose -f docker-compose.simple.yml up --build -d

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo ERROR: Forkmark failed to start. See the output above for details.
    echo.
    pause
    exit /b 1
)

echo.
echo  ==============================
echo   Forkmark is running!
echo   Open http://localhost:7700
echo  ==============================
echo.
echo To stop Forkmark, run stop.bat
echo.

:: Try to open the browser automatically
start "" http://localhost:7700

pause
