param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectPath 'runtime\livingmemory'
& $Python -m venv $environmentPath
if ($LASTEXITCODE -ne 0) { throw 'Cannot create memory Python environment.' }
& (Join-Path $environmentPath 'Scripts\python.exe') -m pip install -r (Join-Path $projectPath 'extensions\plugins\livingmemory\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Memory dependencies failed to install.' }
Write-Output 'Memory environment installed. Ollama is NOT started.'
Write-Output 'Place the independent Ollama distribution in runtime\ollama; models go in runtime\ollama\models.'
