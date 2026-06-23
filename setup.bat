@echo off
setlocal

echo --- Advanced Sender Ultra - Automated Setup ---

:: --- Step 1: Check for Python ---
echo.
echo [1/6] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not found in your system's PATH.
    echo Please install Python 3.8+ and ensure it's added to your PATH.
    pause
    exit /b 1
)
echo Python found.

:: --- Step 2: Create Virtual Environment ---
echo.
echo [2/6] Setting up virtual environment...
if not exist .venv (
    echo Creating virtual environment in '.venv\'...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

:: --- Step 3: Install Python Dependencies ---
echo.
echo [3/6] Installing required Python packages...
call .venv\Scripts\activate.bat

:: --- "Smarter" Preliminary Step: Ensure core tools are present ---
echo Upgrading core packaging tools (pip, setuptools)...
python -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo ERROR: Failed to upgrade core packaging tools.
    pause
    exit /b 1
)

pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install one or more Python packages.
    echo Please review the errors above. This can be caused by network issues or package conflicts.
    echo You can try running this command manually for more details:
    echo.
    echo   .venv\Scripts\pip.exe install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo All Python packages installed successfully.

:: --- Step 4: Check for OpenSSL ---
echo.
echo [4/6] Checking for OpenSSL (for DKIM/S-MIME features)...
where openssl >nul 2>&1
if %errorlevel% equ 0 (
    echo OpenSSL found.
) else (
    echo WARNING: OpenSSL was not found in your PATH. S/MIME features will not work.
    echo.
    echo --- Attempting to install Git for Windows (which includes OpenSSL) using winget... ---
    winget install --id Git.Git -e --source winget
    if %errorlevel% equ 0 (
        echo.
        echo --- Git for Windows has been installed. ---
        echo Please close this window and re-run setup.bat to ensure OpenSSL is detected in the new PATH.
        pause
        exit /b 0
    ) else (
        echo.
        echo --- winget install failed or was not available. ---
        echo To use S/MIME features, you must install OpenSSL manually.
        echo The easiest way is to install Git for Windows from: https://git-scm.com/download/win
        echo During installation, ensure you select the option that adds Git to your system PATH.
    )
)

:: --- Step 5: Create Default Config Files ---
echo.
echo [5/6] Checking for configuration files...
if not exist "config\config.ini" (
    echo 'config.ini' not found. Creating from example...
    copy "config\config.ini.example" "config\config.ini"
)
if not exist ".env" (
    echo '.env' file not found. Creating an empty one for your secrets...
    echo # Add your secrets here, e.g., HUNTER_API_KEY="your_key" > .env
)

:: --- Step 6: Initialize Database ---
echo.
echo [6/6] Initializing the state database...
.venv\Scripts\python.exe database_manager.py

echo.
echo --- Setup Complete! ---
echo You can now add your SMTP servers and API keys to 'config\config.ini' and '.env'.
echo Then, run 'run.bat' to start the application.
pause