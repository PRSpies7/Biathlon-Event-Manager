@echo off
setlocal EnableExtensions
title Biathlon Event Manager v1.15.1

cd /d "%~dp0"

echo.
echo ============================================================
echo             Biathlon Event Manager v1.15.1
echo ============================================================
echo.

REM ------------------------------------------------------------
REM 1. Check whether Python is installed
REM ------------------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py"
    goto :python_found
)

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=python"
    goto :python_found
)

echo Python was not found on this computer.
echo.
echo Biathlon Event Manager requires Python 3.10 or later.
echo.
echo Please open PowerShell or Command Prompt and run:
echo.
echo     winget install Python.Python.3.12
echo.
echo After Python has finished installing, close this window
echo and double-click run_app.bat again.
echo.
pause
exit /b 1

:python_found
echo Python found.

REM ------------------------------------------------------------
REM 2. Create the application's private virtual environment
REM    automatically if it does not already exist.
REM ------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo First-time setup: creating the application's Python environment...
    "%PY_CMD%" -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create the Python environment.
        echo.
        pause
        exit /b 1
    )
    echo Python environment created successfully.
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

REM ------------------------------------------------------------
REM 3. Check whether the required packages are available.
REM ------------------------------------------------------------
"%VENV_PY%" -c "import streamlit, pandas, openpyxl, pdfplumber" >nul 2>&1
if errorlevel 1 goto :install_packages

echo Required packages are already installed.
goto :start_app

:install_packages
echo.
echo Required Python packages are not installed.
echo.
choice /C YN /N /M "Would you like to install them now? [Y/N] "
if errorlevel 2 (
    echo.
    echo Installation cancelled. The application cannot start
    echo until the required packages are installed.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing required packages...
echo.

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo ERROR: Could not update pip.
    echo.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Package installation failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Required packages installed successfully.

:start_app
echo.
echo Starting Biathlon Event Manager...
echo.
echo The application will open in your browser.
echo Keep this window open while using the application.
echo.

"%VENV_PY%" -m streamlit run app.py

echo.
echo ============================================================
echo The Biathlon Event Manager has stopped.
echo ============================================================
echo.
pause
