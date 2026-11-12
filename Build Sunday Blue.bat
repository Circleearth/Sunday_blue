@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
set "build_result=%errorlevel%"
if not "%build_result%"=="0" echo Build failed. Read the message above. Your data was not deleted.
if "%build_result%"=="0" echo Ready: SundayBlue.exe. Keep its companion folders.
pause
exit /b %build_result%
