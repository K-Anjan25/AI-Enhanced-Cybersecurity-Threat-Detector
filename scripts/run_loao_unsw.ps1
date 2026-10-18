# Leave-one-attacker-out on UNSW-NB15 (Windows PowerShell 5.1 or PowerShell 7).
#
# For each attacker source: hold it out for test, train the baselines and FlowNet
# on the rest, and write one run log per model. Then write one summary table.
#
# Run from the repository root, with the venv active:
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\run_loao_unsw.ps1                       # 15% sample (default)
#   .\scripts\run_loao_unsw.ps1 -DataDir data\raw\unsw  # full corpus (needs ~16 GB RAM)
#
# Input: headered_1..4.csv in -DataDir, made by scripts\prepare_unsw_raw.py.

param(
    [string]$DataDir = "data\raw\unsw_s15",
    [string[]]$Holdouts = @("175.45.176.0", "175.45.176.1", "175.45.176.2", "175.45.176.3"),
    [int]$Epochs = 6,
    [string]$RunsDir = "data\runs"
)

$ErrorActionPreference = "Stop"

if (-not $env:VIRTUAL_ENV) {
    throw "Activate the venv first: .\.venv\Scripts\Activate.ps1"
}

$files = @()
foreach ($i in 1..4) {
    $path = Join-Path $DataDir "headered_$i.csv"
    if (-not (Test-Path $path)) {
        throw "Missing $path. Run: python scripts\prepare_unsw_raw.py --src data\raw\unsw --out $DataDir [--sample-frac 0.15]"
    }
    $files += "--file"
    $files += $path
}

New-Item -ItemType Directory -Force $RunsDir | Out-Null

foreach ($holdout in $Holdouts) {
    Write-Host ""
    Write-Host "=== Holding out $holdout : baselines ==="
    & python scripts\run_baselines.py --dataset unsw-nb15 @files `
        --split-policy leave-one-attacker-out --holdout-entity $holdout --key source `
        --out (Join-Path $RunsDir "loao_baselines_$holdout.json")
    if ($LASTEXITCODE -ne 0) { throw "run_baselines failed for holdout $holdout (exit $LASTEXITCODE)" }

    Write-Host ""
    Write-Host "=== Holding out $holdout : FlowNet ($Epochs epochs) ==="
    & python scripts\train_flownet.py --dataset unsw-nb15 @files `
        --split-policy leave-one-attacker-out --holdout-entity $holdout --key source `
        --epochs $Epochs `
        --out (Join-Path $RunsDir "loao_flownet_$holdout.json")
    if ($LASTEXITCODE -ne 0) { throw "train_flownet failed for holdout $holdout (exit $LASTEXITCODE)" }
}

Write-Host ""
Write-Host "=== Summary ==="
& python scripts\summarise_loao.py --runs $RunsDir --out (Join-Path $RunsDir "loao_summary")
if ($LASTEXITCODE -ne 0) { throw "summary failed (exit $LASTEXITCODE)" }
Write-Host ""
Write-Host "Done. Table: $(Join-Path $RunsDir 'loao_summary.md')"
