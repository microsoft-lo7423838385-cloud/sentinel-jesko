@echo off
echo --- WeasyPrint PDF Engine Setup (GTK3 for Windows) ---
echo This script will attempt to install the required GTK3 runtime for PDF generation.
echo It requires the Windows Package Manager (winget), which is standard on modern Windows 10/11.
echo.
echo Searching for winget...
winget --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] winget command not found.
    echo Please update your system via Windows Update or install 'App Installer' from the Microsoft Store.
    pause
    exit /b 1
)
echo winget found.
echo.
echo Installing GTK3 runtime...
winget install --id=tschoonj.GTK3-Runtime -e --source winget
echo.
echo [SUCCESS] GTK3 Runtime installation command finished.
echo Please RESTART your computer for the changes to take effect.
echo.
pause