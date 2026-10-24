@echo off
setlocal enabledelayedexpansion
title Qryptex - Academic Document & Math OCR
cd /d "%~dp0"

echo =====================================================================
echo   QRYPTEX - Academic Document & Math OCR
echo   Official Portal: https://qryptex.in
echo =====================================================================
echo.

rem 1. Check for Python (specifically prioritizing Python 3.11)
set "PY_CMD="

where py >nul 2>&1
if %errorlevel%==0 (
    py -3.11 --version >nul 2>&1
    if !errorlevel!==0 (
        set "PY_CMD=py -3.11"
        echo [OK] Using Python 3.11 via py launcher.
    ) else (
        py -3 --version >nul 2>&1
        if !errorlevel!==0 (
            set "PY_CMD=py -3"
            echo [OK] Using default Python via py launcher.
        )
    )
)

if not defined PY_CMD (
    where python >nul 2>&1
    if !errorlevel!==0 (
        set "PY_CMD=python"
        echo [OK] Using system python on PATH.
    )
)

rem Fallback: Check standard Python 3.11 installation locations
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        echo [OK] Detected Python 3.11 in LocalAppData.
    ) else if exist "%ProgramFiles%\Python311\python.exe" (
        set "PY_CMD=%ProgramFiles%\Python311\python.exe"
        echo [OK] Detected Python 3.11 in Program Files.
    )
)

if not defined PY_CMD (
    echo [!] Python was not detected on your system.
    echo     Attempting to install Python 3.11 automatically via winget...
    echo.
    where winget >nul 2>&1
    if !errorlevel!==0 (
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        if !errorlevel!==0 (
            echo.
            echo [OK] Python 3.11 installed successfully.
            set "PY_CMD=py -3.11"
        )
    )
    if not defined PY_CMD (
        echo [X] Python is not installed.
        echo     Please install Python 3.11 (64-bit) from:
        echo     https://www.python.org/downloads/release/python-3119/
        echo     NOTE: Ensure "Add python.exe to PATH" is checked during setup.
        echo.
        pause
        exit /b 1
    )
)

rem 2. Check for Tesseract OCR
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo [OK] Tesseract OCR detected at C:\Program Files\Tesseract-OCR.
) else if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" (
    echo [OK] Tesseract OCR detected in LocalAppData.
) else (
    echo [i] Tesseract OCR not detected.
    echo     Math equation recognition works 100%% out of the box.
    echo     For full document text, install Tesseract from:
    echo     https://github.com/UB-Mannheim/tesseract/wiki
)
echo.

echo Starting Qryptex backend server...
echo Web Interface URL: http://127.0.0.1:8000
echo (Keep this window open while using the application)
echo.

%PY_CMD% scripts\launch.py %*

if %errorlevel% neq 0 (
    echo.
    echo =====================================================================
    echo [!] Server exited with code %errorlevel%.
    echo     Please check the messages above for details.
    echo =====================================================================
    pause
)
