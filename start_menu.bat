@echo off
REM Simple wrapper to reliably start the menu and keep the window open.
cd /d "%~dp0"
echo Starting Advanced Sender via wrapper...
REM Use CALL with a quoted path to avoid Explorer parsing quirks.
call "%~dp0run.bat"
echo Returned from run.bat. Press any key to close this window.
pause
