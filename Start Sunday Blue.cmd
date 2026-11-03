@echo off
cd /d "%~dp0"
if exist "%~dp0SundayBlue.exe" (
  start "" "%~dp0SundayBlue.exe"
) else (
  start "" python main.py
)
