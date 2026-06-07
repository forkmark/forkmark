@echo off
setlocal EnableDelayedExpansion
title Forkmark

:: ============================================================
::  Forkmark — Windows Launcher
::  No Python, no Node required.
::  Requires: Docker Desktop (installed automatically if missing)
:: ============================================================

set FM_PORT=7700
set FM_URL=http://localhost:%FM_PORT%
set COMPOSE_FILE=docker-compose.simple.yml
set DOCKER_INSTALL_URL=https://www.docker.com/products/docker-desktop/

:: ── Banner ────────────────────────────────────────────────────────────────────
cls
echo.
echo   =====================================================
echo    Forkmark  ^|  AI Workflow QA Platform
echo   =====================================================
call :detect_system
echo.

:: ── Step 1: Check Docker ──────────────────────────────────────────────────────
where docker >nul 2>&1
if %errorlevel% neq 0 (
    color 0E
    echo   Docker Desktop not found.
    echo.
    echo   Forkmark runs inside Docker — a free container runtime.
    echo   Install it from:  %DOCKER_INSTALL_URL%
    echo.
    echo   Steps:
    echo     1. Download and run the Docker Desktop installer
    echo     2. Restart your computer if prompted
    echo     3. Open Docker Desktop and wait for the whale icon
    echo     4. Run start.bat again
    echo.
    set /p OPEN_BROWSER="  Open the Docker download page now? [Y/n] "
    if /i "!OPEN_BROWSER!" neq "n" (
        start "" "%DOCKER_INSTALL_URL%"
    )
    goto :end_pause
)

:: ── Step 2: Check Docker Compose ─────────────────────────────────────────────
docker compose version >nul 2>&1
set COMPOSE_V2=%errorlevel%
if %COMPOSE_V2% equ 0 (
    set "COMPOSE_CMD=docker compose"
) else (
    where docker-compose >nul 2>&1
    if %errorlevel% equ 0 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        color 0C
        echo   Docker is installed but Docker Compose was not found.
        echo   Please update Docker Desktop to the latest version.
        echo   %DOCKER_INSTALL_URL%
        goto :end_pause
    )
)

:: ── Step 3: Check Docker daemon ───────────────────────────────────────────────
docker info >nul 2>&1
if %errorlevel% neq 0 (
    color 0E
    echo   Docker Desktop is installed but not running.
    echo.
    echo   Please:
    echo     1. Open Docker Desktop from the Start menu
    echo     2. Wait for the whale icon in the system tray (bottom-right)
    echo     3. Run start.bat again
    echo.
    set /p RETRY="  Retry now (after starting Docker)? [Y/n] "
    if /i "!RETRY!" neq "n" (
        docker info >nul 2>&1
        if %errorlevel% neq 0 (
            echo.
            echo   Docker still not running. Please start it and try again.
            goto :end_pause
        )
    ) else (
        goto :end_pause
    )
)

:: ── Step 4: First-run .env setup ─────────────────────────────────────────────
if not exist ".env" (
    echo   First-run setup
    echo   ---------------------------------------------------
    echo   Forkmark can use an AI API key for LLM judge
    echo   scoring (OpenAI or OpenRouter). This is optional.
    echo.
    set /p FM_API_KEY="  API key (press Enter to skip): "
    echo.
    if "!FM_API_KEY!" neq "" (
        echo OPENAI_API_KEY=!FM_API_KEY!> .env
        echo FM_OPENAI_API_KEY=!FM_API_KEY!>> .env
    ) else (
        echo # Add your API key here to enable LLM judge scoring:> .env
        echo # OPENAI_API_KEY=sk-...>> .env
    )
)

:: ── Step 5: Start Forkmark ───────────────────────────────────────────────────
echo   Starting Forkmark...
echo   (First run builds the image — takes about 2 minutes)
echo   (Subsequent starts are instant)
echo.

%COMPOSE_CMD% -f %COMPOSE_FILE% up --build -d
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo   ERROR: Failed to start Forkmark. See the output above.
    goto :end_pause
)

:: ── Step 6: Wait for server to be ready ──────────────────────────────────────
echo.
echo   Waiting for Forkmark to be ready
set ATTEMPTS=0
:health_loop
    set /a ATTEMPTS+=1
    if %ATTEMPTS% gtr 45 (
        echo.
        echo   Forkmark is taking longer than expected.
        echo   Open %FM_URL% in your browser manually.
        goto :success_print
    )
    :: Use PowerShell for the HTTP check (available on all modern Windows)
    powershell -NoProfile -Command ^
        "try { $r = Invoke-WebRequest '%FM_URL%/api/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" ^
        >nul 2>&1
    if %errorlevel% equ 0 goto :health_ok
    <nul set /p ".=."
    powershell -NoProfile -Command "Start-Sleep -Milliseconds 2000" >nul 2>&1
    goto :health_loop

:health_ok
echo.  OK

:success_print
color 0A
echo.
echo   =====================================================
echo    Forkmark is running!
echo    Open:  %FM_URL%
echo   =====================================================
echo.
echo   To stop Forkmark, run stop.bat
echo.

:: ── Step 7: Open browser ─────────────────────────────────────────────────────
start "" "%FM_URL%"
goto :end_no_pause

:detect_system
    :: Detect CPU architecture
    if "%PROCESSOR_ARCHITECTURE%" == "AMD64" (
        set FM_ARCH=x86_64
    ) else if "%PROCESSOR_ARCHITECTURE%" == "ARM64" (
        set FM_ARCH=arm64
    ) else (
        set FM_ARCH=%PROCESSOR_ARCHITECTURE%
    )
    echo   Platform : Windows / %FM_ARCH%
    exit /b 0

:end_pause
echo.
pause
exit /b 1

:end_no_pause
exit /b 0
