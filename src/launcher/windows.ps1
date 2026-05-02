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
