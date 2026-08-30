@echo off
setlocal
cd /d "%~dp0backend"

echo ================================================
echo   ERP System - Setup ^& Run
echo ================================================
echo.

if not exist ".venv" (
    echo [1/5] Creating Python virtual environment...
    python -m venv .venv
) else (
    echo [1/5] Virtual environment already exists, skipping.
)

call .venv\Scripts\activate.bat

echo [2/5] Installing dependencies...
pip install -r requirements.txt -q

if not exist "..\frontend\vendor\tailwind.js" (
    echo [3/5] First-time setup: downloading offline assets...
    echo        ^(this step needs internet ONCE - never again after this^)
    python -m scripts.vendor_assets
    if errorlevel 1 (
        echo.
        echo WARNING: could not download offline assets - check your internet
        echo connection and re-run this file. The app will not look correct
        echo without this step completing successfully at least once.
        pause
    )
) else (
    echo [3/5] Offline assets already downloaded, skipping.
)

if not exist "erp_system.db" (
    echo [4/5] Setting up the database with sample data...
    python -m scripts.seed_data
) else (
    echo [4/5] Database already exists, skipping sample data setup.
)

echo [5/5] Starting the app...
start "ERP System Server (keep this window open)" cmd /k "call .venv\Scripts\activate.bat && uvicorn app.main:app --port 8000"

echo.
echo Waiting for the server to start...
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"

echo.
echo ================================================
echo   Done. The app should now be open in your browser.
echo   A second window ("ERP System Server") is running
echo   the app - keep it open while you use the program.
echo   Closing that window stops the app.
echo ================================================
pause
