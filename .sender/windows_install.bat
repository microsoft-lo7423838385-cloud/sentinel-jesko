@echo off
setlocal

:: =======================================================
::  Windows Installation Script for Advanced Sender ultra
:: =======================================================
::  This script performs the following actions:
::  1. Sets the PowerShell execution policy to allow the script to run.
::  2. Executes the main 'install.ps1' PowerShell script.

echo Starting the installation process...
echo This may require administrator privileges to install missing software.
echo.

:: Run the main PowerShell installation script
PowerShell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0\install.ps1'"

echo.
echo Installation script finished.
endlocal
pause