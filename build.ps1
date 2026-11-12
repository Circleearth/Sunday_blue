param([string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!$Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = (& py -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $Python = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    }
}
if (!$Python -or !(Test-Path -LiteralPath $Python)) { throw 'Install Python, or run build.ps1 -Python <python.exe>.' }
& $Python -c 'import PyInstaller, PySide6, requests, regex'
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies missing. Run: py -3 -m pip install -r requirements-build.txt' }
$exe = Join-Path $PSScriptRoot 'SundayBlue.exe'
function Assert-AppClosed {
    $running = Get-Process SundayBlue -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }
    if ($running) { throw 'Exit Sunday Blue from its tray menu before building. No process was terminated.' }
}
Assert-AppClosed
# Do not collect unrelated DLLs from editor/tool environments (e.g. Poppler ICU).
$originalPath = $env:PATH
$pythonHome = Split-Path -Parent $Python
$env:PATH = @($pythonHome, (Join-Path $pythonHome 'Scripts'), (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
try {
& $Python -m PyInstaller --noconfirm --clean --distpath build/dist --workpath build/work SundayBlue.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed; installed application was not changed.' }
} finally { $env:PATH = $originalPath }
$output = Join-Path $PSScriptRoot 'build/dist/SundayBlue'
$check = Start-Process -FilePath (Join-Path $output 'SundayBlue.exe') -ArgumentList '--verify-package' -PassThru -WindowStyle Hidden
if (!$check.WaitForExit(90000)) { $check.Kill(); throw 'Isolated package verification timed out; installed application was not changed.' }
if ($check.ExitCode -ne 0) { throw "Package verification failed; see $output/package-check.json. Installed application was not changed." }
Assert-AppClosed
$checkpoint = Join-Path $PSScriptRoot ('build/previous/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $checkpoint -Force | Out-Null
$internal = Join-Path $PSScriptRoot '_internal'
$hadExe = Test-Path -LiteralPath $exe
$hadInternal = Test-Path -LiteralPath $internal
if ($hadExe) { Copy-Item -LiteralPath $exe -Destination $checkpoint }
if ($hadInternal) { Move-Item -LiteralPath $internal -Destination (Join-Path $checkpoint '_internal') }
try {
    Copy-Item -LiteralPath (Join-Path $output '_internal') -Destination $internal -Recurse
    Copy-Item -LiteralPath (Join-Path $output 'SundayBlue.exe') -Destination $exe -Force
} catch {
    if (Test-Path -LiteralPath $internal) { Move-Item -LiteralPath $internal -Destination (Join-Path $checkpoint 'failed-internal') }
    if ($hadInternal) { Move-Item -LiteralPath (Join-Path $checkpoint '_internal') -Destination $internal }
    if ($hadExe) { Copy-Item -LiteralPath (Join-Path $checkpoint 'SundayBlue.exe') -Destination $exe -Force }
    throw
}
Write-Output "Built: $exe"
Write-Output "Previous executable/runtime: $checkpoint"
Write-Output 'Keep _internal, assets, personas, extensions, data and runtime beside the EXE.'
Write-Output 'User data and external document folders were not changed.'
