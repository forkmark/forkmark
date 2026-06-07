@echo off
title Forkmark — Load Demo Data
color 0B

echo.
echo  ======================================
echo   Forkmark — Load Demo Data
echo  ======================================
echo.
echo  This will populate Forkmark with 8 pre-built demo scenarios:
echo.
echo    1. Retail       — Customer Support Triage
echo    2. Healthcare   — Clinical Note Summarization
echo    3. Legal        — Contract Clause Risk Review
echo    4. FinServ      — Fraud Alert Explanation
echo    5. HR           — Job Description Generator
echo    6. Sales        — Cold Outreach Email Personalization
echo    7. Engineering  — Bug Report Triage
echo    8. Model Migration — gpt-3.5-turbo vs gpt-4o-mini
echo.
echo  Estimated time: 2-3 minutes
echo.

:: Check Docker is available
where docker >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo ERROR: Docker not found. Please run run.bat first.
    echo.
    pause
    exit /b 1
)

:: Check Forkmark container is running
docker inspect forkmark >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo ERROR: Forkmark is not running.
    echo.
    echo Please run run.bat first, then try again.
    echo.
    pause
    exit /b 1
)

docker inspect --format="{{.State.Running}}" forkmark 2>nul | findstr /I "true" >nul
if %errorlevel% neq 0 (
    color 0C
    echo ERROR: Forkmark container exists but is not running.
    echo.
    echo Please run run.bat first, then try again.
    echo.
    pause
    exit /b 1
)

echo Starting demo seeder...
echo (You can watch Forkmark fill up at http://localhost:7700)
echo.

docker exec -it forkmark python3 /app/examples/run_all_demos.py

if %errorlevel% neq 0 (
    color 0E
    echo.
    echo  Some demos may have failed — check the output above.
    echo  Any demos that succeeded are visible at http://localhost:7700
    echo.
    pause
    exit /b 1
)

echo.
echo  ======================================
echo   Demo data loaded!
echo   Open http://localhost:7700
echo  ======================================
echo.
echo  Tip: Click any workflow to explore comparisons,
echo  divergence scores, and reviewer decisions.
echo.

start "" http://localhost:7700

pause
