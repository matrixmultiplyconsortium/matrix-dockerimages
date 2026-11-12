# ==============================================================================
# Distributed Matrix Multiply — 1-Click Worker Node Installer (Windows / WSL2)
#
# Auto-detects compute hardware (NVIDIA GPU, AMD ROCm, AMD SEV-SNP, Intel TDX, CPU),
# verifies Docker Desktop & WSL2 container runtime, configures worker Nostr keypair,
# enables zero-config outbound-only NAT traversal, and renders operator dashboard.
# ==============================================================================

[CmdletBinding()]
param (
    [Alias("p")]
    [string]$PayoutAddress = "",

    [Alias("r")]
    [string]$Relays = "wss://relay.matrix-compute.net",

    [Alias("s")]
    [string]$SettlementUrl = "http://settlement.matrix-compute.net:8000",

    [double]$SatsPerGflop = 0.00001,

    [int]$MinTaskSats = 1,

    [string]$EnvFile = "$HOME\.matrix\worker.env",

    [switch]$DryRun,

    [ValidateSet("nvidia", "rocm", "sev-snp", "tdx", "cpu", "")]
    [string]$MockHardware = "",

    [Alias("y")]
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

# Colors
function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[-] $Message" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Distributed Matrix Multiply -- Worker Bootstrap (Windows / WSL2) ===" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Verify Python Runtime
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        try {
            $code = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
            & $cmd -c $code 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonCmd = $cmd
                break
            }
        } catch { }
    }
}

if (-not $PythonCmd) {
    Write-ErrorMsg -Message "Python 3.8+ is required. Please install Python from https://www.python.org/"
    exit 1
}
$pyVer = & $PythonCmd --version 2>&1
Write-Success -Message "Python runtime verified: $pyVer"

# 2. Check Docker Desktop / WSL2 Runtime
$DockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $DockerCmd) {
    if ($DryRun) {
        Write-Warn -Message "Docker not detected on host (skipped in -DryRun mode)"
    } else {
        Write-ErrorMsg -Message "Docker Desktop is not installed or not in PATH. Please install Docker Desktop: https://www.docker.com/products/docker-desktop/"
        exit 1
    }
} else {
    $dockerVer = & docker --version 2>&1
    Write-Success -Message "Docker CLI detected: $dockerVer"
    if (-not $DryRun) {
        & docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorMsg -Message "Docker Desktop engine is not running. Please start Docker Desktop."
            exit 1
        }
        Write-Success -Message "Docker engine connectivity confirmed"
    }
}

# 3. Hardware and TEE Detection Cascade
Write-Info -Message "Probing system compute capabilities and enclaves..."
$probeArgs = @("-m", "scripts.onboard", "probe")
if ($MockHardware) {
    $probeArgs += @("--mock", $MockHardware)
}

Push-Location $ScriptDir
try {
    $probeOutputJson = & $PythonCmd $probeArgs | Out-String
} finally {
    Pop-Location
}

$hwObj = $probeOutputJson | ConvertFrom-Json
$isGpu = $hwObj.is_gpu
$isTee = $hwObj.is_tee
$hwVendor = $hwObj.vendor
$hwModel = $hwObj.model
$hwTflops = $hwObj.tflops
$teeType = if ($hwObj.tee_type) { $hwObj.tee_type } else { "None" }

Write-Success "Detected Hardware: $hwModel ($hwVendor) -- $hwTflops TFLOPS FP32"
if ($isTee) {
    Write-Success "Confidential Computing Enclave: $teeType"
}

# 4. Identity & Configuration File
$resolvedEnv = [System.IO.Path]::GetFullPath([System.Environment]::ExpandEnvironmentVariables($EnvFile))

if (Test-Path $resolvedEnv) {
    Write-Info "Existing worker configuration found at $resolvedEnv"
    $envLines = Get-Content $resolvedEnv
    $workerPrivkey = ""
    $workerNpub = ""
    $workerNsec = ""
    $savedPayout = ""

    foreach ($line in $envLines) {
        if ($line -match "^MATRIX_WORKER_PRIVKEY=(.*)$") { $workerPrivkey = $matches[1].Trim() }
        if ($line -match "^MATRIX_WORKER_NPUB=(.*)$") { $workerNpub = $matches[1].Trim() }
        if ($line -match "^MATRIX_WORKER_NSEC=(.*)$") { $workerNsec = $matches[1].Trim() }
        if ($line -match "^MATRIX_WORKER_PAYOUT_ADDRESS=(.*)$") { $savedPayout = $matches[1].Trim() }
    }
    if (-not $PayoutAddress -and $savedPayout) {
        $PayoutAddress = $savedPayout
    }
} else {
    Write-Info "Generating new worker Nostr Secp256k1 identity..."
    $keygenArgs = @("-m", "scripts.onboard", "keygen", "--output", $resolvedEnv)
    if ($PayoutAddress) {
        $keygenArgs += @("--payout-address", $PayoutAddress)
    }
    Push-Location $ScriptDir
    try {
        $keygenOutputJson = & $PythonCmd $keygenArgs | Out-String
    } finally {
        Pop-Location
    }
    $keyObj = $keygenOutputJson | ConvertFrom-Json
    $workerPrivkey = $keyObj.hex_privkey
    $workerNpub = $keyObj.npub
    $workerNsec = $keyObj.nsec
    Write-Success "Created worker identity: $workerNpub"
}

# Payout address fallback
if (-not $PayoutAddress -and -not $NonInteractive -and [System.Environment]::UserInteractive) {
    $prompt = Read-Host "Enter Lightning Address or LNURL for earnings payout (or press Enter to skip)"
    if ($prompt) {
        $PayoutAddress = $prompt
    }
}
if (-not $PayoutAddress) {
    $PayoutAddress = "worker@matrix-compute.com"
}

# 5. Determine Docker Container Specification
if ($isGpu) {
    $containerImage = "matrixcompute/worker:gpu"
    if ($hwVendor -eq "NVIDIA") {
        $gpuFlags = "--gpus all --ipc=host"
    } else {
        $gpuFlags = "--device=/dev/kfd --device=/dev/dri --ipc=host"
    }
} else {
    $containerImage = "matrixcompute/worker:latest"
    $gpuFlags = ""
}

$teeFlags = ""
if ($teeType -eq "AMD_SEV_SNP") {
    $teeFlags = "--device=/dev/sev-guest"
} elseif ($teeType -eq "INTEL_TDX") {
    $teeFlags = "--device=/dev/tdx_guest"
}

$dockerRunCmd = "docker run -d `
  --name matrix-worker `
  --restart unless-stopped `
  --network host `
  $gpuFlags `
  $teeFlags `
  -e MATRIX_WORKER_PRIVKEY=""$workerPrivkey"" `
  -e MATRIX_WORKER_NPUB=""$workerNpub"" `
  -e MATRIX_WORKER_PAYOUT_ADDRESS=""$PayoutAddress"" `
  -e MATRIX_WORKER_NOSTR_RELAYS=""$Relays"" `
  -e MATRIX_WORKER_SETTLEMENT_API_URL=""$SettlementUrl"" `
  -e MATRIX_WORKER_SATS_PER_GFLOP=""$SatsPerGflop"" `
  -e MATRIX_WORKER_MIN_TASK_SATS=""$MinTaskSats"" `
  -e MATRIX_WORKER_NAT_MODE=""reverse_tunnel"" `
  $containerImage"

# 6. Execute or Simulate Run
if ($DryRun) {
    Write-Info "Dry-Run Active. Generated Docker Execution Command:"
    Write-Host ""
    Write-Host $dockerRunCmd -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Info "Launching compute worker container..."
    $existing = & docker ps -a --format '{{.Names}}' | Select-String -Pattern "^matrix-worker$"
    if ($existing) {
        Write-Info "Replacing existing matrix-worker container..."
        & docker rm -f matrix-worker 2>&1 | Out-Null
    }
    Invoke-Expression $dockerRunCmd | Out-Null
    Write-Success "Worker container started successfully"
}

# 7. Render Operator Dashboard
$dashArgs = @(
    "-m", "scripts.onboard", "dashboard",
    "--payout", $PayoutAddress,
    "--npub", $workerNpub,
    "--nat-mode", "OUTBOUND-ONLY NAT",
    "--tier", "PROBATIONARY"
)
if ($MockHardware) {
    $dashArgs += @("--mock", $MockHardware)
}

Write-Host ""
Push-Location $ScriptDir
try {
    & $PythonCmd $dashArgs
} finally {
    Pop-Location
}
Write-Host ""
Write-Success "Setup complete! Worker is connected and listening for matrix tile jobs via outbound reverse tunnel."
Write-Host ""
