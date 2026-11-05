@echo off
rem Install the qq-reminders silent daemon as a per-user Windows Task Scheduler task
rem (watchdog style: runs hourly, only spawns if no daemon is alive - the daemon
rem itself enforces a single instance via a pid lock file, so frequent triggers are
rem safe and consume nothing when one is already running).
setlocal
set "ROOT=%~dp0..\..\"
set "PYTHONW=C:\Users\zsc18\AppData\Local\Programs\Python\Python314\pythonw.exe"
set "VBS=%TEMP%\sb_qq_reminders_launch.vbs"
set "DAEMON=%ROOT%extensions\plugins\qq-reminders\daemon\run.py"
echo Set sh = CreateObject("WScript.Shell")> "%VBS%"
echo sh.Run """""%PYTHONW%"%"" ""%DAEMON%"", 0, False>> "%VBS%"
echo Set sh = Nothing>> "%VBS%"
schtasks /Create /F /SC HOURLY /TN "SundayBlue-QQ-Reminders" /TR "wscript.exe \"%VBS%\"" /RL LIMITED 2>nul
if %errorlevel%==0 (
  schtasks /Change /TN "SundayBlue-QQ-Reminders" /ENABLE
  echo Installed: task SundayBlue-QQ-Reminders (hourly, silent, self-healing)
) else (
  echo schtasks failed - running as administrator may be required, or start the daemon manually:
  echo   wscript.exe "%VBS%"
)
rem Start it right now without a window
start "" wscript.exe "%VBS%"
endlocal
