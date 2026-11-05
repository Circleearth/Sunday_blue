@echo off
rem qq-reminders: stop the daemon and remove its watchdog task.
rem Thin wrapper around the plugin's daemon_ctl.stop; delivered reminder
rem history in state.sqlite3 is left untouched.
setlocal
for %%i ("%~dp0..\..\..\") do set "ROOT=%%~fi"
set "PY=C:\Users\zsc18\AppData\Local\Programs\Python\Python314\python.exe"
"%PY%" -c "import sys;sys.path.insert(0,sys.argv[1]+chr(92)+'extensions'+chr(92)+'plugins'+chr(92)+'qq-reminders');import daemon_ctl;print('stopped:',daemon_ctl.stop(sys.argv[1]))" "%ROOT%"
pause
endlocal
