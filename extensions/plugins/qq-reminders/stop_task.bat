@echo off
setlocal
schtasks /Delete /F /TN "SundayBlue-QQ-Reminders" 2>nul
for /f "tokens=2" %%i in ('wmic process where "CommandLine like '%%run.py%%' and Name='pythonw.exe'" get ProcessId /value 2^>nul ^| findstr ProcessId") do (
  set "PID=%%i"
  set "PID=%PID: =%"
  taskkill /PID %PID% /F 2>nul
)
echo qq-reminders daemon task removed and any running daemon stopped.
endlocal
