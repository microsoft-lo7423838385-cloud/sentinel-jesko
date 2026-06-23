@echo off
title Advanced Sender ultra - Setup & Launch

:: --- "World-Class" Fix: Enable delayed expansion for variables inside loops ---
setlocal enabledelayedexpansion

:: --- "Smarter" Bootstrapper ---
:: This script is now intelligent. It will be verbose on the first run
:: and silent on all subsequent runs for a cleaner user experience.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "VENV_DIR=.venv"

:: Check if this is a first run (venv doesn't exist)
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    goto :FIRST_RUN
) else (
    goto :NORMAL_RUN
)

:FIRST_RUN
    echo --- Advanced Sender ultra (First Time Setup) ---

    echo Checking for Python installation...
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not found in your system's PATH.
        echo Please install Python 3.10 or higher and ensure it's added to your PATH.
        pause
        exit /b
    )
    echo Python found.

    echo Virtual environment not found. Creating one...
    python -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b
    )
    echo Virtual environment created successfully.

    call "%VENV_DIR%\Scripts\activate.bat"
    echo Virtual environment activated.

    echo Installing required packages (this may take a moment)...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install packages. Please check your internet connection.
        pause
        exit /b
    )
    echo All packages installed.
    goto :COMMON_SETUP

:NORMAL_RUN
    :: This is the quiet path for subsequent launches
    call "%VENV_DIR%\Scripts\activate.bat"
    :: Quietly check for updates to requirements.txt
    pip install -r requirements.txt --quiet
    goto :COMMON_SETUP

:COMMON_SETUP
    :: --- Configuration File Setup (runs every time, but only acts if needed) ---
    set "CONFIG_DIR=config"
    set "CONFIG_FILE=%CONFIG_DIR%\config.ini"
    set "CONFIG_EXAMPLE=%CONFIG_DIR%\config.ini.example"

    if not exist "%CONFIG_FILE%" (
        if exist "%CONFIG_EXAMPLE%" (
            echo Configuration file not found. Creating from example...
            if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
            copy "%CONFIG_EXAMPLE%" "%CONFIG_FILE%" >nul
        )
    )

    :: --- Launch the Main Application ---
    :MENU_LOOP
    echo Starting the Advanced Sender ultra menu...
    :: The menu script now controls its own loop. It will return a non-zero exit code
    :: only when the user chooses to exit the entire application.
    "%VENV_DIR%\Scripts\python.exe" menu.py
    if %errorlevel% equ 0 (
        :: A return code of 0 means an action finished and we should loop back to the menu.
        cls
        goto :MENU_LOOP
    )

    :: Any other error code means the user chose to exit from the menu.
    echo Menu exited.
    )

    :: Keep window open if launched with -keepopen argument
    :END
    echo.
    echo Script finished.
