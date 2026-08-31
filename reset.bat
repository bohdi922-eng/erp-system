@echo off
setlocal
cd /d "%~dp0backend"

echo ================================================
echo   ERP System - Reset Data
echo ================================================
echo.
echo This deletes EVERYTHING currently in the program
echo (sales, repairs, customers, messages...) and
echo replaces it with fresh sample data.
echo.
echo IMPORTANT: close the app first if it's running -
echo right-click the ERP System icon in your system
echo tray (bottom-right, near the clock) and choose
echo "إغلاق البرنامج". Windows can't delete the database
echo file while the app still has it open.
echo.
set /p CONFIRM="Are you sure? Type Y and press Enter to continue: "
if /i not "%CONFIRM%"=="Y" (
    echo Cancelled - nothing was deleted.
    pause
    exit /b
)

if not exist ".venv" (
    echo Virtual environment not found - run setup.bat first.
    pause
    exit /b
)

call .venv\Scripts\activate.bat
python -m scripts.reset_data

echo.
echo Done. Run setup.bat to start the app again.
pause
