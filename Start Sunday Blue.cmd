@echo off
cd /d "%~dp0"
if exist "%~dp0SundayBlue.exe" (
  start "" "%~dp0SundayBlue.exe"
  exit /b 0
)
rem 源码模式：用 pythonw 静默启动（无控制台窗口）
where pythonw >nul 2>nul
if errorlevel 1 (
  echo 未找到 pythonw（真实 Python，非 Windows Store 别名），无法启动源码模式。
  echo 请确认已安装 Python 且 PATH 指向 C:\...\Programs\Python\Python3xx\pythonw.exe，
  echo 或先运行 build.ps1 生成 SundayBlue.exe。
  pause
  exit /b 1
)
start "" pythonw main.py
rem 给它 3 秒启动，若进程已消失说明启动即崩，提示去查
ping -n 4 127.0.0.1 >nul
tasklist /fi "imagename eq pythonw.exe" 2>nul | find pythonw >nul
if errorlevel 1 (
  echo 源码模式启动后 pythonw 未检测到运行中进程，可能启动失败。
  echo 请手动运行一次带控制台的命令查看报错：
  echo   py main.py
  echo （注意：PATH 里的 python 可能是 Microsoft Store 别名，会静默失败；用 py 或真实 pythonw）
  pause
  exit /b 1
)
exit /b 0
