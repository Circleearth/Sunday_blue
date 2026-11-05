@echo off
rem qq-reminders watchdog installer (thin wrapper around the plugin's daemon_ctl).
rem Safe to re-run: the daemon's pid-lock dedupes, so this is a no-op if it is
rem already running. This only manages THIS plugin's task + its own daemon; it
rem does not touch the host app data or the Rui dsh QQ gateway.
setlocal
rem %~dp0 = <root>\extensions\plugins\qq-reminders\ ; go up three levels to root
for %%i ("%~dp0..\..\..\") do set "ROOT=%%~fi"
set "PY=C:\Users\zsc18\AppData\Local\Programs\Python\Python314\python.exe"
"%PY%" -c "import sys;sys.path.insert(0,sys.argv[1]+chr(92)+'extensions'+chr(92)+'plugins'+chr(92)+'qq-reminders');import daemon_ctl;print('installed:',daemon_ctl.install(sys.argv[1]))" "%ROOT%"
pause
endlocal
