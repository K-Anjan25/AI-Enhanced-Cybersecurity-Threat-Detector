# Leave-one-attacker-out on UNSW-NB15, run in Docker containers in parallel.
#
# Same inputs, same arguments, same output files as run_loao_unsw.ps1. The difference is that
# the holdouts run at the same time, one container each, instead of one after another. Each
# container runs the baselines and then FlowNet for its holdout (scripts/loao_one_holdout.py).
#
# Resources are sized from what Docker Desktop actually gives the VM (docker info), not from the
# Windows total, so a memory cap is never higher than the VM can supply.
#
# Containers that succeed are removed. A container that fails is kept, so its log can be read,
# and the script stops before the summary.
#
# Run from the repository root, with the venv active (the summary runs on the host):
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\run_loao_docker.ps1
#
# Optional:
#   .\scripts\run_loao_docker.ps1 -Parallel 2            # cap concurrent containers
#   .\scripts\run_loao_docker.ps1 -SkipBuild             # reuse an existing image

param(
    [string]$DataDir = "data\raw\unsw_s15",
    [string[]]$Holdouts = @("175.45.176.0", "175.45.176.1", "175.45.176.2", "175.45.176.3"),
    [int]$Epochs = 6,
    [string]$RunsDir = "data\runs",
    [string]$Image = "aegis-train",
    [int]$Parallel = 0,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

if (-not $env:VIRTUAL_ENV) {
    throw "Activate the venv first (the summary runs on the host): .\.venv\Scripts\Activate.ps1"
}

# Docker's stderr is a native-command error under Stop, so relax the preference for this probe.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$null = docker version --format '{{.Server.Version}}' 2>$null
$dockerExit = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($dockerExit -ne 0) {
    throw "Docker engine is not reachable. Open Docker Desktop, wait until it says 'Engine running', then run: docker version"
}

$repo = (Resolve-Path ".").Path
$dataPath = Join-Path $repo $DataDir
foreach ($i in 1..4) {
    $file = Join-Path $dataPath "headered_$i.csv"
    if (-not (Test-Path $file)) {
        throw "Missing $file. Run: python scripts\prepare_unsw_raw.py --src data\raw\unsw --out $DataDir [--sample-frac 0.15]"
    }
}

New-Item -ItemType Directory -Force (Join-Path $repo $RunsDir) | Out-Null
$logDir = Join-Path $repo (Join-Path $RunsDir "logs")
New-Item -ItemType Directory -Force $logDir | Out-Null

# Size the containers from the Docker VM, not the host.
$vmMemMB = [math]::Floor([double](docker info --format '{{.MemTotal}}') / 1MB)
$vmCpus = [int](docker info --format '{{.NCPU}}')
# Leave 20 percent of the VM memory free; each training container needs about 1.5 GB.
$usableMB = [math]::Floor($vmMemMB * 0.8)
$fitByMemory = [math]::Max(1, [math]::Floor($usableMB / 1536))
if ($Parallel -le 0) {
    $Parallel = [math]::Max(1, [math]::Min($Holdouts.Count, [math]::Min($fitByMemory, $vmCpus)))
}
$memoryPerRun = [math]::Min(4096, [math]::Floor($usableMB / $Parallel))
$cpusPerRun = [math]::Max(1, [math]::Floor($vmCpus / $Parallel))
Write-Host "Docker VM: $vmCpus CPUs, $vmMemMB MB. Running $Parallel container(s) at a time, $cpusPerRun CPU and $memoryPerRun MB each."
if ($Parallel -eq 1 -and $Holdouts.Count -gt 1) {
    Write-Host "Only one container fits: raise Docker Desktop memory (Settings > Resources) to about 6 GB, then re-run."
}

if (-not $SkipBuild) {
    Write-Host "Building $Image from ml-service (torch is cached after the first build)."
    docker build -t $Image (Join-Path $repo "ml-service")
    if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE)" }
}

$worker = {
    param($image, $mount, $name, $memory, $cpus, $holdout, $data, $runs, $epochs, $log)
    & docker run --name $name --no-healthcheck --memory "${memory}m" --cpus $cpus -v $mount -w /work $image `
        python scripts/loao_one_holdout.py $holdout $data $runs $epochs *> $log
    $LASTEXITCODE
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$mount = "${repo}:/work"
$running = @{}
foreach ($holdout in $Holdouts) {
    while ((@(Get-Job -State Running)).Count -ge $Parallel) { Start-Sleep -Seconds 5 }
    $safe = $holdout -replace '\.', '-'
    $name = "aegis-loao-$safe-$stamp"
    $log = Join-Path $logDir "loao_$holdout.log"
    Write-Host "Starting $holdout in container $name (log: $log)"
    $job = Start-Job -ScriptBlock $worker -ArgumentList @(
        $Image, $mount, $name, $memoryPerRun, $cpusPerRun, $holdout,
        ($DataDir -replace '\\', '/'), ($RunsDir -replace '\\', '/'), $Epochs, $log
    )
    $running[$job.Id] = @{ holdout = $holdout; name = $name; log = $log }
}

Get-Job | Wait-Job | Out-Null

$failed = @()
foreach ($job in Get-Job) {
    $info = $running[$job.Id]
    $code = @(Receive-Job $job)[-1]
    if ($code -eq 0) {
        docker rm $info.name | Out-Null
        Write-Host "OK    $($info.holdout)  (container removed)"
    } else {
        $failed += $info
        Write-Host "FAIL  $($info.holdout)  exit $code  container kept: $($info.name)  log: $($info.log)"
    }
    Remove-Job $job
}

if ($failed.Count -gt 0) {
    throw "$($failed.Count) holdout(s) failed. Read the kept logs, fix the cause, then re-run with -Holdouts set to the failed ones. The summary reads every run in the folder."
}

Write-Host ""
Write-Host "=== Summary ==="
& python scripts\summarise_loao.py --runs $RunsDir --out (Join-Path $RunsDir "loao_summary")
if ($LASTEXITCODE -ne 0) { throw "summary failed (exit $LASTEXITCODE)" }
Write-Host ""
Write-Host "Done. Table: $(Join-Path $RunsDir 'loao_summary.md')"
