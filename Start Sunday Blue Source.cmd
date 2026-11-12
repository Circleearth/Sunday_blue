@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 main.py
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw main.py
  exit /b 0
)
echo Python launcher not found. Install Python to run source mode.
pause
exit /b 1
