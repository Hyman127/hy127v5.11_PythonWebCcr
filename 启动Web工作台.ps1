param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $ProjectRoot.TrimEnd('\')

$GlobalDir    = "$env:LOCALAPPDATA\Hy127Web"
$RuntimeFile  = "$GlobalDir\hub_runtime.json"
$InstallFile  = "$GlobalDir\install.json"
$TokenDir     = "$GlobalDir\keys"
$ScriptRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ForceRestartHub = $false

# 1. Discover install paths.
if (-not (Test-Path $InstallFile)) {
    Write-Host '  [!] install.json not found'
    Write-Host '  [!] Please run the installer first'
    exit 1
}
$install = Get-Content $InstallFile -Raw -Encoding UTF8 | ConvertFrom-Json

# Developer checkout override: prefer this folder when it contains .venv + hy127web.
$LocalPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
$LocalHubApp = Join-Path $ScriptRoot "hy127web\hub\app.py"
$LocalWorkerApp = Join-Path $ScriptRoot "hy127web\worker\app.py"
if ((Test-Path $LocalPython) -and (Test-Path $LocalHubApp) -and (Test-Path $LocalWorkerApp)) {
    Write-Host "  [i] local dev workbench detected; using current folder"
    $ForceRestartHub = $true
    $ProjectRoot = $ScriptRoot
    $GlobalDir = Join-Path $ScriptRoot ".web-workbench\global"
    $RuntimeFile = Join-Path $GlobalDir "hub_runtime.json"
    $TokenDir = Join-Path $GlobalDir "keys"
    New-Item -ItemType Directory -Force -Path $GlobalDir, $TokenDir | Out-Null
    $install = [pscustomobject]@{
        install_root    = $ScriptRoot
        python_path     = $LocalPython
        hub_app_path    = $LocalHubApp
        worker_app_path = $LocalWorkerApp
        static_path     = (Join-Path $ScriptRoot "hy127web\static")
        version         = "dev"
    }
}

if (-not (Test-Path $install.python_path)) {
    Write-Host "  [!] Python not found: $($install.python_path)"
    exit 1
}
if (-not (Test-Path $install.hub_app_path)) {
    Write-Host "  [!] Web workbench files not found"
    Write-Host "  [!] Please update or reinstall the Web workbench package"
    exit 1
}

& $install.python_path -c "import fastapi, uvicorn, httpx, websockets" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [!] Web runtime dependencies are incomplete"
    Write-Host "  [!] Run: uv pip install -r hy127web\requirements.txt --python .\.venv\Scripts\python.exe --cache-dir .\.uv-cache"
    exit 1
}

$installRoot = $install.install_root
if ([string]::IsNullOrWhiteSpace($installRoot)) {
    $installRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $install.hub_app_path))
}
if (-not (Test-Path $installRoot)) {
    Write-Host "  [!] Web workbench root not found: $installRoot"
    exit 1
}
if (Test-Path -LiteralPath $ProjectRoot) {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath
} else {
    Write-Host "  [!] Project root not found, falling back to script root: $ProjectRoot"
    $ProjectRoot = $ScriptRoot
}

# 2. Reuse a live Hub if runtime metadata is still valid.
$hubUrl = $null
$runtime = $null

if ($ForceRestartHub -and (Test-Path $RuntimeFile)) {
    try {
        $oldRuntime = Get-Content $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($oldRuntime.pid) {
            Stop-Process -Id ([int]$oldRuntime.pid) -Force -ErrorAction SilentlyContinue
        }
    } catch { }
    Remove-Item $RuntimeFile -Force -ErrorAction SilentlyContinue
}

if (Test-Path $RuntimeFile) {
    try {
        $runtime = Get-Content $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $testUrl = "$($runtime.base_url)/api/hub/identity"
        $resp = Invoke-WebRequest $testUrl -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            $hubUrl = $runtime.base_url
            Write-Host "  [i] connected to Hub ($hubUrl)"
        }
    } catch {
        $runtime = $null
    }
}

# 3. Start Hub when needed.
if ($null -eq $hubUrl) {
    Write-Host '  [i] starting Hub...'

    $env:HY127WEB_INSTALL_ROOT = $installRoot
    $env:HY127WEB_PYTHON_PATH = $install.python_path
    $env:HY127WEB_GLOBAL_DIR = $GlobalDir
    $env:CODE880WEB_INSTALL_ROOT = $installRoot
    $env:CODE880WEB_PYTHON_PATH = $install.python_path
    $env:CODE880WEB_GLOBAL_DIR = $GlobalDir
    $logDir = Join-Path $GlobalDir "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $hubStdoutLog = Join-Path $logDir "hub-startup.out.log"
    $hubStderrLog = Join-Path $logDir "hub-startup.err.log"
    Remove-Item $hubStdoutLog, $hubStderrLog -Force -ErrorAction SilentlyContinue

    Start-Process -FilePath $install.python_path `
        -ArgumentList @("-m", "hy127web.hub.app") `
        -WorkingDirectory $installRoot `
        -RedirectStandardOutput $hubStdoutLog `
        -RedirectStandardError $hubStderrLog `
        -WindowStyle Hidden -PassThru | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Path $RuntimeFile) {
            try {
                $runtime = Get-Content $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
                $testUrl = "$($runtime.base_url)/api/hub/identity"
                $r = Invoke-WebRequest $testUrl -TimeoutSec 1 -UseBasicParsing
                if ($r.StatusCode -eq 200) {
                    $hubUrl = $runtime.base_url
                    $ready = $true
                    break
                }
            } catch { }
        }
    }

    if (-not $ready) {
        Write-Host '  [!] Hub startup timeout'
        Write-Host "  [!] stdout log: $hubStdoutLog"
        Write-Host "  [!] stderr log: $hubStderrLog"
        if (Test-Path $hubStderrLog) {
            Get-Content $hubStderrLog -Tail 20
        }
        exit 1
    }
    Write-Host "  [OK] Hub started ($hubUrl)"
}

# 4. Read launch token.
$tokenFile = $null
if ($runtime -and $runtime.launch_token_path) {
    $tokenFile = $runtime.launch_token_path
}
if ([string]::IsNullOrWhiteSpace($tokenFile)) {
    $tokenFile = Join-Path $TokenDir "launch_token"
}
if (-not (Test-Path $tokenFile)) {
    Write-Host "  [!] launch token not found: $tokenFile"
    exit 1
}
$launchToken = (Get-Content $tokenFile -Raw).Trim()

# 5. Register current project.
Write-Host '  [i] registering current project...'
$jsonContentType = 'application/json; charset=utf-8'
$regBody = @{ root_path = $ProjectRoot } | ConvertTo-Json -Compress
$regBodyBytes = [System.Text.Encoding]::UTF8.GetBytes($regBody)
$regHeaders = @{
    'Authorization' = "Bearer $launchToken"
}

try {
    $regResp = Invoke-RestMethod -Method POST `
        -Uri "$hubUrl/internal/projects/register" `
        -Body $regBodyBytes -Headers $regHeaders `
        -ContentType $jsonContentType -TimeoutSec 10
    $workspaceId = $regResp.workspace_id
    Write-Host "  [OK] project registered (ID: $workspaceId)"
} catch {
    Write-Host "  [!] project registration failed: $_"
    exit 1
}

# 6. Create one-time bootstrap code and open browser.
try {
    $codeBody = @{ target = "/w/$workspaceId" } | ConvertTo-Json -Compress
    $codeBodyBytes = [System.Text.Encoding]::UTF8.GetBytes($codeBody)
    $codeResp = Invoke-RestMethod -Method POST `
        -Uri "$hubUrl/internal/bootstrap-code" `
        -Body $codeBodyBytes -Headers $regHeaders `
        -ContentType $jsonContentType -TimeoutSec 5
    $openUrl = "$hubUrl/bootstrap?code=$($codeResp.code)"
} catch {
    $openUrl = $hubUrl
}

Start-Process $openUrl
Write-Host ''
Write-Host '  [OK] Web workbench launched. Please continue in your browser.'
Write-Host '  [OK] Closing this window will not stop the Web workbench.'
