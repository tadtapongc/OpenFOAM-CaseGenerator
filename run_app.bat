@echo off
setlocal enabledelayedexpansion

title Rapidamente CFD Studio - OpenFOAM Case Generator

echo ======================================================================
echo    OpenFOAM Studio - Case Generator & Cluster Dispatcher
echo ======================================================================
echo.

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.9+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Virtual environment directory
set "VENV_DIR=%~dp0.venv"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [*] Creating virtual environment in .venv...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtualenv
call "%VENV_DIR%\Scripts\activate.bat"

:: Check and install dependencies
echo [*] Checking web dependencies...
pip install -e ".[web]" --quiet

echo.
echo [*] Starting CFD Studio Web Server...
echo [*] Browser will open automatically at http://127.0.0.1:8000
echo.

python -m cfd_gen.web.server

pause
