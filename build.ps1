param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -m PyInstaller --noconfirm --clean --distpath build/dist --workpath build/work SundayBlue.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build/dist/SundayBlue/SundayBlue.exe') -Destination (Join-Path $PSScriptRoot 'SundayBlue.exe') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build/dist/SundayBlue/_internal') -Destination $PSScriptRoot -Recurse -Force
Write-Output 'Built SundayBlue.exe. Keep _internal, assets, personas, extensions and data beside it.'
