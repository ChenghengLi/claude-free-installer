# install-claude-free-windows.ps1 — one-shot installer for `claude-free` on Windows.
#
# Installs Claude Code routed through the free-claude-code NVIDIA NIM proxy,
# with all /model tiers (Opus/Sonnet/Haiku/fallback) mapped to MiniMax M2.5.
#
# Usage (in PowerShell):
#   irm https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 | iex
#
# Or download then run:
#   iwr https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 -OutFile install-claude-free-windows.ps1
#   .\install-claude-free-windows.ps1
#
# If you get an execution-policy error, run once:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
# Idempotent — re-running it skips already-done steps.

$ErrorActionPreference = "Stop"
# PowerShell treats native-command stderr (uv progress, git clone status, etc.)
# as terminating errors when ErrorActionPreference is "Stop". Disable that
# behaviour for native commands. Variable exists in PS 7.3+; ignored on 5.1.
try { $PSNativeCommandUseErrorActionPreference = $false } catch {}

function Step($msg)  { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan -NoNewline; Write-Host "" }
function Ok($msg)    { Write-Host " OK  $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "WARN  $msg" -ForegroundColor Yellow }
function Errm($msg)  { Write-Host "ERR   $msg" -ForegroundColor Red }
function Have($cmd)  { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$Repo = Join-Path $HOME "free-claude-code"
$LocalBin = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force -Path $LocalBin | Out-Null

# ----------------------------------------------------------------------------
Step "1/8  Prerequisites: git, python"
if (-not (Have "git")) {
    Errm "git is required. Install Git for Windows from https://git-scm.com/download/win and re-run."
    exit 1
}
if (-not (Have "python") -and -not (Have "python3")) {
    Errm "python is required. Install Python 3 from https://www.python.org/downloads/windows/ (tick 'Add Python to PATH') and re-run."
    exit 1
}
$python = if (Have "python3") { "python3" } else { "python" }
Ok "git + $python present"

# ----------------------------------------------------------------------------
Step "2/8  NVIDIA API key"
$envFile = Join-Path $Repo ".env"
$existingKey = $null
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^NVIDIA_NIM_API_KEY=' | Select-Object -First 1
    if ($line) {
        $val = ($line.Line -replace '^NVIDIA_NIM_API_KEY="?([^"]*)"?', '$1')
        if ($val -like "nvapi-*") { $existingKey = $val }
    }
}
if ($existingKey) {
    Write-Host "Existing key found in $envFile ($($existingKey.Substring(0,12))...)"
    $ans = Read-Host "Reuse it? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") { $script:NvApiKey = $existingKey }
}
if (-not $script:NvApiKey) {
    Write-Host "Get a free key at: https://build.nvidia.com/settings/api-keys"
    Write-Host "(developer tier — no credit card, ~40 req/min)"
    $script:NvApiKey = Read-Host "Paste your NVIDIA API key (nvapi-...)"
}
if (-not $script:NvApiKey) { Errm "no key entered"; exit 1 }
if ($script:NvApiKey -notlike "nvapi-*") { Warn "key does not start with 'nvapi-' — continuing" }
Ok "key captured"

# ----------------------------------------------------------------------------
Step "3/8  uv (Python package manager)"
if (-not (Have "uv")) {
    irm https://astral.sh/uv/install.ps1 | iex
}
$uvBin = Join-Path $HOME ".local\bin"
$env:PATH = "$uvBin;$env:PATH"
if (-not (Have "uv")) { Errm "uv not on PATH after install"; exit 1 }
uv --version
Ok "uv ready"

# ----------------------------------------------------------------------------
Step "4/8  Claude Code"
if (-not (Have "claude")) {
    irm https://claude.ai/install.ps1 | iex
}
$env:PATH = "$uvBin;$env:PATH"
if (-not (Have "claude")) {
    Errm "claude install failed; try manually: irm https://claude.ai/install.ps1 | iex"
    exit 1
}
try { claude --version } catch {}
Ok "claude ready"

# ----------------------------------------------------------------------------
Step "5/8  fzf (model picker)"
if (-not (Have "fzf")) {
    $tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP "fzf-$(Get-Random)") -Force
    $url = "https://github.com/junegunn/fzf/releases/download/v0.55.0/fzf-0.55.0-windows_amd64.zip"
    $zip = Join-Path $tmp.FullName "fzf.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp.FullName -Force
    Move-Item -Path (Join-Path $tmp.FullName "fzf.exe") -Destination (Join-Path $LocalBin "fzf.exe") -Force
    Remove-Item -Recurse -Force $tmp.FullName
}
& (Join-Path $LocalBin "fzf.exe") --version
Ok "fzf ready"

# ----------------------------------------------------------------------------
Step "6/8  Cloning free-claude-code + uv sync"
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    # git writes its progress to stderr; wrap via cmd.exe to silence stderr
    # cleanly under PowerShell 5.1's strict-error mode.
    cmd /c "git clone https://github.com/Alishahryar1/free-claude-code.git `"$Repo`" 2>NUL"
    if ($LASTEXITCODE -ne 0) { Errm "git clone failed (exit $LASTEXITCODE)"; exit 1 }
} else {
    Write-Host "repo already at $Repo"
}
Push-Location $Repo
try {
    Write-Host "Installing Python 3.14 via uv (downloads ~22 MB on first run)..."
    # Redirect stderr to $null so uv's progress messages don't trigger
    # PowerShell 5.1's NativeCommandError under ErrorActionPreference=Stop.
    cmd /c "uv python install 3.14 2>NUL"
    Write-Host "Running uv sync (may take a minute on first run)..."
    cmd /c "uv sync --quiet 2>NUL"
    if ($LASTEXITCODE -ne 0) { cmd /c "uv sync 2>NUL" }
    if (-not (Test-Path (Join-Path $Repo "nvidia_nim_models.json"))) {
        try {
            Invoke-WebRequest -Uri "https://integrate.api.nvidia.com/v1/models" `
                -Headers @{ "Authorization" = "Bearer $script:NvApiKey" } `
                -OutFile (Join-Path $Repo "nvidia_nim_models.json") -UseBasicParsing
        } catch {
            Warn "couldn't fetch nvidia_nim_models.json (model picker won't work until you do)"
        }
    }
} finally { Pop-Location }
Ok "repo ready"

# ----------------------------------------------------------------------------
Step "7/8  Writing $envFile (tiers: all MiniMax M2.5)"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Repo ".env.example") $envFile
}

function Set-EnvKvp($file, $key, $value) {
    $content = Get-Content $file -Raw
    $line = "$key=`"$value`""
    if ($content -match "(?m)^$key=") {
        $content = [regex]::Replace($content, "(?m)^$key=.*$", $line)
    } else {
        if (-not $content.EndsWith("`n")) { $content += "`n" }
        $content += $line + "`n"
    }
    Set-Content -Path $file -Value $content -NoNewline
}

Set-EnvKvp $envFile "NVIDIA_NIM_API_KEY"   $script:NvApiKey
Set-EnvKvp $envFile "ANTHROPIC_AUTH_TOKEN" "freecc"
Set-EnvKvp $envFile "MODEL_OPUS"           "nvidia_nim/minimaxai/minimax-m2.5"
Set-EnvKvp $envFile "MODEL_SONNET"         "nvidia_nim/minimaxai/minimax-m2.5"
Set-EnvKvp $envFile "MODEL_HAIKU"          "nvidia_nim/minimaxai/minimax-m2.5"
Set-EnvKvp $envFile "MODEL"                "nvidia_nim/minimaxai/minimax-m2.5"
Ok ".env configured"

# ----------------------------------------------------------------------------
Step "8/8  Installing claude-free.ps1 launcher + audit script to $LocalBin"

# --- audit script (used by `claude-free audit` / `claude-free calibrate`) ---
$auditUrl  = "https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py"
$auditPath = Join-Path $LocalBin "claude-free-audit.py"
try {
    Invoke-WebRequest -Uri $auditUrl -OutFile $auditPath -UseBasicParsing
} catch {
    Warn "couldn't fetch claude-free-audit.py from $auditUrl -- ``claude-free audit`` won't work until you do"
}

$launcherPath = Join-Path $LocalBin "claude-free.ps1"
$launcher = @'
# claude-free.ps1 — launch Claude Code through the free-claude-code NVIDIA NIM proxy.
#
# Subcommands:
#   claude-free                  start proxy if needed, launch claude
#   claude-free pick             interactive NVIDIA NIM model picker (fzf)
#   claude-free audit            probe NVIDIA NIM models for TTFT + code benchmarks
#   claude-free calibrate        walk by code-score, pick first with TTFT <= 1s, set .env
#   claude-free update           refresh the audit script + benchmarks table from GitHub
#   claude-free models / status  show /model tier mapping + proxy status
#   claude-free stop             kill the running proxy
#   claude-free logs             show proxy log
#   claude-free help             this help

$Repo    = Join-Path $HOME "free-claude-code"
$Port    = 8082
$LogFile = Join-Path $Repo "claude-free-proxy.log"
$PidFile = Join-Path $Repo "claude-free-proxy.pid"
$EnvFile = Join-Path $Repo ".env"

function Read-Env($key) {
    if (-not (Test-Path $EnvFile)) { return "" }
    $line = Select-String -Path $EnvFile -Pattern "^\s*$key\s*=" | Select-Object -Last 1
    if (-not $line) { return "" }
    $v = ($line.Line -split "=", 2)[1].Trim()
    $v = $v -replace '^["'']', '' -replace '["'']$', ''
    return $v
}

function Test-ProxyUp {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.SendTimeout = 500; $c.ReceiveTimeout = 500
        $iar = $c.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500)
        if ($ok -and $c.Connected) { $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}

function Start-Proxy {
    if (Test-ProxyUp) {
        Write-Host "proxy already up on :$Port" -ForegroundColor DarkGray
        return $true
    }
    Push-Location $Repo
    try {
        Write-Host "starting proxy on :$Port (log: $LogFile)" -ForegroundColor DarkGray
        # Start-Process refuses to redirect stdout & stderr to the same file,
        # so route through cmd.exe and let the shell do the redirect (>log 2>&1).
        $cmdLine = "uv run uvicorn server:app --host 127.0.0.1 --port $Port > `"$LogFile`" 2>&1"
        $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $cmdLine) `
            -WindowStyle Hidden -PassThru
        $proc.Id | Out-File -FilePath $PidFile -Encoding ascii
        for ($i=0; $i -lt 80; $i++) {
            Start-Sleep -Milliseconds 250
            if (Test-ProxyUp) { Write-Host "proxy ready" -ForegroundColor Green; return $true }
            if ($proc.HasExited) {
                Write-Host "proxy died during startup. Tail of log:" -ForegroundColor Red
                Get-Content $LogFile -Tail 30
                return $false
            }
        }
        Write-Host "proxy failed to start in 20s. Tail of log:" -ForegroundColor Red
        Get-Content $LogFile -Tail 30
        return $false
    } finally { Pop-Location }
}

function Stop-Proxy {
    if (Test-Path $PidFile) {
        $procId = (Get-Content $PidFile).Trim()
        # /T = kill the process tree (cmd.exe -> uv -> uvicorn -> python)
        # /F = force; redirect to NUL so a missing pid doesn't print scary text
        cmd /c "taskkill /PID $procId /T /F >NUL 2>NUL"
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "stopped pid $procId" -ForegroundColor Green
    }
    # Belt + suspenders: kill any stray python.exe whose command line contains uvicorn
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "uvicorn" } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }
}

function Show-Models {
    if (Test-ProxyUp) {
        Write-Host "proxy up on :$Port" -ForegroundColor Green
        if (Test-Path $PidFile) { Write-Host ("  pid: " + (Get-Content $PidFile)) }
    } else {
        Write-Host "proxy not running" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "/model tier mapping (what each Claude Code label actually runs):"
    "  Opus      (label: 'Opus 4.7')   -> {0}"   -f (Read-Env "MODEL_OPUS")   | ForEach-Object { Write-Host $_ -ForegroundColor Green }
    "  Sonnet    (label: 'Sonnet 4.6') -> {0}"   -f (Read-Env "MODEL_SONNET") | ForEach-Object { Write-Host $_ -ForegroundColor Green }
    "  Haiku     (label: 'Haiku 4.5')  -> {0}"   -f (Read-Env "MODEL_HAIKU")  | ForEach-Object { Write-Host $_ -ForegroundColor Green }
    "  Fallback  (MODEL=)              -> {0}"   -f (Read-Env "MODEL")        | ForEach-Object { Write-Host $_ -ForegroundColor Green }
}

function Show-Help {
    Write-Host @"
claude-free — Claude Code via the free-claude-code NVIDIA NIM proxy

usage:
  claude-free                  start proxy if needed, launch claude
  claude-free pick             interactive NVIDIA NIM model picker (fzf)
  claude-free audit            probe NIM chat models for TTFT + code benchmarks
                               flags: --all  --filter <s>  --include <id>  --runs N
                                      --by {combined,ttft,code}  --tau MS
                                      --rate REQ_MIN  --early-exit  --threshold MS
                                      --set  --no-set
  claude-free calibrate        walk models by code-score, pick first with TTFT <= 1s
                               and write it to .env. Same flags as audit, e.g.:
                                 claude-free calibrate --threshold 500
                                 claude-free calibrate --filter qwen
  claude-free update           refresh ~/.local/bin/claude-free-audit.py from GitHub
                               (gets you new models + updated benchmark scores)
  claude-free models|status    show /model tier mapping + proxy status
  claude-free stop             kill the running proxy
  claude-free logs             show last 80 lines of the proxy log
  claude-free help             this help

config: $EnvFile
log:    $LogFile
"@
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "no .env at $EnvFile — clone Alishahryar1/free-claude-code first" -ForegroundColor Red
    exit 1
}
$key = Read-Env "NVIDIA_NIM_API_KEY"
if (-not $key) {
    Write-Host "NVIDIA_NIM_API_KEY is empty in $EnvFile" -ForegroundColor Red
    exit 1
}
$token = Read-Env "ANTHROPIC_AUTH_TOKEN"
if (-not $token) { $token = "freecc" }

$AuditScript = Join-Path $HOME ".local\bin\claude-free-audit.py"
function Get-PyExe {
    if (Get-Command python  -ErrorAction SilentlyContinue) { return "python"  }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return "python3" }
    return $null
}

$cmd = if ($args.Count -gt 0) { $args[0] } else { "" }
switch -Regex ($cmd) {
    "^pick$" {
        if (-not (Start-Proxy)) { exit 1 }
        Push-Location $Repo
        try { & bash ./claude-pick @($args | Select-Object -Skip 1) } finally { Pop-Location }
    }
    "^audit$" {
        if (-not (Test-Path $AuditScript)) {
            Write-Host "audit script missing at $AuditScript" -ForegroundColor Red
            Write-Host "re-run the installer or fetch:" -ForegroundColor DarkGray
            Write-Host "  iwr https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py -OutFile `"$AuditScript`""
            exit 1
        }
        $py = Get-PyExe
        if (-not $py) { Write-Host "python is not on PATH" -ForegroundColor Red; exit 1 }
        & $py $AuditScript @($args | Select-Object -Skip 1)
        exit $LASTEXITCODE
    }
    "^calibrate$" {
        if (-not (Test-Path $AuditScript)) {
            Write-Host "audit script missing at $AuditScript" -ForegroundColor Red
            Write-Host "fix: claude-free update" -ForegroundColor DarkGray
            exit 1
        }
        $py = Get-PyExe
        if (-not $py) { Write-Host "python is not on PATH" -ForegroundColor Red; exit 1 }
        # `calibrate` = walk benchmarked models top-down by code-score, pick
        # the first one whose TTFT is <= 1000ms, write to .env. Forwards extras
        # so users can pass --threshold / --filter / --runs / etc.
        & $py $AuditScript "--set" "--early-exit" "--threshold" "1000" @($args | Select-Object -Skip 1)
        exit $LASTEXITCODE
    }
    "^update$" {
        $url = "https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py"
        Write-Host "claude-free update -- refreshing audit script + benchmarks table" -ForegroundColor Cyan
        Write-Host "  fetching $url"
        $tmp = "$AuditScript.new"
        try {
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
            Move-Item -Path $tmp -Destination $AuditScript -Force
            Write-Host "updated $AuditScript" -ForegroundColor Green
        } catch {
            if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
            Write-Host "fetch failed -- keeping existing script" -ForegroundColor Red
            Write-Host $_.Exception.Message
            exit 1
        }
    }
    "^(stop|kill)$" { Stop-Proxy }
    "^(status|models)$" { Show-Models }
    "^(logs|log)$" {
        if (Test-Path $LogFile) { Get-Content $LogFile -Tail 80 } else { Write-Host "no log yet" }
    }
    "^(help|-h|--help)$" { Show-Help }
    default {
        if (-not (Start-Proxy)) { exit 1 }
        $env:ANTHROPIC_BASE_URL = "http://localhost:$Port"
        $env:ANTHROPIC_AUTH_TOKEN = $token
        Write-Host ""
        Write-Host "claude-free via NVIDIA NIM (free) — /model tiers route to:"
        "  Opus   -> {0}"             -f (Read-Env "MODEL_OPUS")   | ForEach-Object { Write-Host $_ -ForegroundColor Green }
        "  Sonnet -> {0}  (default)"  -f (Read-Env "MODEL_SONNET") | ForEach-Object { Write-Host $_ -ForegroundColor Green }
        "  Haiku  -> {0}"             -f (Read-Env "MODEL_HAIKU")  | ForEach-Object { Write-Host $_ -ForegroundColor Green }
        Write-Host ""
        & claude @args
    }
}
'@
Set-Content -Path $launcherPath -Value $launcher -Encoding UTF8

# Wrapper .cmd so users can type `claude-free` (without .ps1) from any shell
$cmdPath = Join-Path $LocalBin "claude-free.cmd"
$cmdContent = "@echo off`r`npowershell -ExecutionPolicy Bypass -NoProfile -File `"%~dp0claude-free.ps1`" %*`r`n"
Set-Content -Path $cmdPath -Value $cmdContent -Encoding ASCII

Ok "claude-free installed"

# ----------------------------------------------------------------------------
Step "Final  PATH check"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$LocalBin*") {
    [Environment]::SetEnvironmentVariable("Path", "$LocalBin;$userPath", "User")
    Warn "added $LocalBin to your User PATH — open a NEW terminal for it to take effect"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Open a NEW terminal, then run:"
Write-Host ""
Write-Host "    claude-free               (launch Claude Code via NVIDIA NIM)"
Write-Host "    claude-free models        (show active /model mapping)"
Write-Host "    claude-free pick          (interactive model picker)"
Write-Host "    claude-free audit         (rank NIM models by latency + code benchmarks)"
Write-Host "    claude-free calibrate     (auto-pick the fastest good model)"
Write-Host "    claude-free update        (refresh audit script + benchmarks table)"
Write-Host "    claude-free stop          (kill the proxy)"
Write-Host "    claude-free help          (full help)"
Write-Host ""
Write-Host "  Config: $envFile"
Write-Host "  Log:    $LogFile"
Write-Host ""
