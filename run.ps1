param(
    [string]$Dataset = (Join-Path $PSScriptRoot 'dataset'),
    [string]$Run = (Join-Path $PSScriptRoot ("run-" + (Get-Date -Format yyyyMMdd-HHmmss)))
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements before running. See README.md.' }
if (-not (Test-Path -LiteralPath $Dataset)) { throw "Dataset missing: $Dataset" }
$evidence = Join-Path $Run 'evidence'
$out = Join-Path $Run 'deliverables'
function Invoke-Step([string]$Script, [string[]]$Arguments) {
    & $python -B (Join-Path $PSScriptRoot $Script) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Script failed with exit code $LASTEXITCODE" }
}
Invoke-Step 'pipeline.py' @($Dataset, $evidence)
Invoke-Step 'report.py' @($evidence, $out)
Invoke-Step 'verify.py' @($evidence)
Write-Output "Verified run: $Run"
