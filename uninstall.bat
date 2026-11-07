@echo off
setlocal
cd /d "%~dp0"

title Antigravity Sound Uninstall

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python was not found! Please install Python and add it to PATH.
    echo.
    pause
    exit /b 1
)

python install.py --uninstall %*

if %errorlevel% neq 0 (
    echo.
    echo [!] An error occurred during uninstall.
    echo.
) else (
    echo.
)

pause
