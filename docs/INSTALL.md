# Installation

This page covers detailed install per OS, what each step does, what files end up where, how to upgrade or uninstall, and what to do when install fails.

For the one-line install commands, see the [README quick install](../README.md#quick-install).

## Prerequisites

You always need:

- A free **NVIDIA API key** (`nvapi-...`) from <https://build.nvidia.com/settings/api-keys> — no credit card, ~40 req/min rate limit.
- A working internet connection (the installer downloads `uv`, `claude`, `fzf`, and clones `free-claude-code`).
- ~500 MB of disk space (mostly Python runtime + `free-claude-code` deps).

Per-OS specifics:

| OS | Pre-install requirement |
|---|---|
| Ubuntu / WSL | `sudo` access to install `apt` packages, or already have `curl git ca-certificates python3` |
| macOS | [Homebrew](https://brew.sh/) installed |
| Windows | [Git for Windows](https://git-scm.com/download/win) + [Python 3](https://www.python.org/downloads/windows/) (with "Add Python to PATH" ticked) |

## What the installer does

All three installers do roughly the same eight steps:

1. **System tools** — `curl git ca-certificates python3` (Ubuntu via `apt`, macOS via `brew`, Windows expects them already).
2. **NVIDIA API key** — prompts for `nvapi-...`, or reuses the saved one in `~/free-claude-code/.env` if present.
3. **`uv`** — installs [Astral's `uv`](https://github.com/astral-sh/uv) Python package manager to `~/.local/bin/uv`.
4. **`claude`** — installs the official Claude Code CLI to `~/.local/bin/claude`.
5. **`fzf`** — installs [fzf](https://github.com/junegunn/fzf) to `~/.local/bin/fzf` (used by `claude-free pick`).
6. **`free-claude-code`** — clones <https://github.com/Alishahryar1/free-claude-code> to `~/free-claude-code/`, installs its Python deps with `uv sync`, and downloads the NVIDIA NIM model catalogue.
7. **`.env`** — writes `~/free-claude-code/.env` with `MODEL_OPUS = MODEL_SONNET = MODEL_HAIKU = MODEL = nvidia_nim/minimaxai/minimax-m2.5` (this is the default tier mapping).
8. **`claude-free` launcher** — writes `~/.local/bin/claude-free` and `~/.local/bin/claude-free-audit.py` (the audit script). Adds `~/.local/bin` to `PATH` if it isn't there yet.

The installer is **idempotent** — re-running it skips already-done steps but always rewrites the launcher and audit script so you get the latest version.

## What ends up where

After install:

```
~/.local/bin/
  claude                  # Claude Code CLI
  claude-free             # Launcher (wraps claude with the proxy)
  claude-free-audit.py    # Audit / calibrate / update script
  uv                      # Python package manager
  fzf                     # Used by `claude-free pick`

~/free-claude-code/
  .env                    # Your NVIDIA key + model tier mapping
  server.js / *.py        # The proxy (uvicorn server:app)
  claude-free-proxy.log   # Runtime log (claude-free logs / rate)
  claude-free-proxy.pid   # PID of the running proxy
  nvidia_nim_models.json  # Cached model catalogue for the picker

~/.claude/                # Shared with native `claude` — sessions, history, projects
```

## Updating an existing install

You have two upgrade paths.

### Refresh just the audit script + benchmarks table

This is the common case — vendor benchmarks update, the `BENCHMARKS` dict in `claude-free-audit.py` gets a new entry, you want the new scores in your `claude-free calibrate` runs:

```bash
claude-free update
```

Atomically replaces `~/.local/bin/claude-free-audit.py` with the latest from `main`. No re-install, no shell restart needed.

### Upgrade everything (launcher + audit + install scripts)

If the launcher itself gained new subcommands, or you're on a pre-`audit`/`calibrate`/`update` install, re-run the installer for your platform. It's idempotent and will preserve your existing `.env` (it'll prompt before reusing the saved API key).

```bash
# Ubuntu / WSL
bash <(curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free.sh)

# macOS
bash <(curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-macos.sh)

# Windows (PowerShell)
irm https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 | iex
```

### Check what version you have

```bash
# Linux / macOS
grep "Last refreshed" ~/.local/bin/claude-free-audit.py
head -3 ~/.local/bin/claude-free-audit.py

# Windows PowerShell
Get-Content $HOME\.local\bin\claude-free-audit.py -TotalCount 3
Select-String "Last refreshed" $HOME\.local\bin\claude-free-audit.py
```

## Uninstalling

There's no one-shot uninstaller, but it's three commands. **Stop the proxy first**, then remove the three things the installer added:

```bash
claude-free stop                              # kill any running proxy
rm -f  ~/.local/bin/claude-free  ~/.local/bin/claude-free-audit.py
rm -rf ~/free-claude-code
```

Optional cleanup:

```bash
rm ~/.local/bin/claude  ~/.local/bin/uv  ~/.local/bin/fzf   # if you don't use these for anything else
rm -rf ~/.claude                                            # WARNING: this nukes Claude Code sessions/history
```

On Windows, the launcher is `~/.local/bin/claude-free.ps1` plus the `.cmd` shim:

```powershell
claude-free stop
Remove-Item $HOME\.local\bin\claude-free.ps1, $HOME\.local\bin\claude-free.cmd, $HOME\.local\bin\claude-free-audit.py
Remove-Item $HOME\free-claude-code -Recurse -Force
```

## Install-time errors

### `sudo: command not found` (containers)

You're root in a minimal container. The installer detects this:

```bash
if [ "$(id -u)" -eq 0 ]; then apt-get install ... ; else sudo apt-get install ...; fi
```

so it should Just Work — but if it doesn't, install the prereqs manually first: `apt-get install -y curl git ca-certificates python3`, then re-run.

### `uv` install fails with "command not found" after install

`~/.local/bin` isn't on your `PATH` yet. The installer appends an `export PATH="$HOME/.local/bin:$PATH"` line to `~/.bashrc` (Linux) or `~/.zshrc` / `~/.bash_profile` (macOS) — but the current shell doesn't pick it up. Open a new terminal, or `source ~/.bashrc`.

### macOS: "operation not permitted" on `xattr -d com.apple.quarantine`

Gatekeeper. The installer tries to clear the quarantine attribute on `fzf`, but if it can't, you'll get a "developer cannot be verified" dialog the first time `claude-free pick` runs. Click "Allow" in System Settings → Privacy & Security.

### Windows: `iex` fails with "running scripts is disabled on this system"

PowerShell execution policy. Run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

then re-run the installer.

### Windows: `python` not on PATH

Reinstall Python 3 from <https://www.python.org/downloads/windows/> with the "Add Python to PATH" box ticked. The installer auto-detects `python` or `python3`; if neither is on PATH, it bails.

### `git clone https://github.com/Alishahryar1/free-claude-code.git` fails

GitHub is down, your network blocks GitHub, or the upstream repo moved. Confirm with `curl -I https://github.com/Alishahryar1/free-claude-code`. If GitHub is up but the repo is gone, file an issue on `claude-free-installer`.

### `uv sync` fails with a Python version error

The installer runs `uv python install 3.14` to get the right interpreter. If that step failed silently (network glitch), re-run the installer — `uv` is now on PATH so the second attempt usually works.

### "couldn't fetch nvidia_nim_models.json"

Your NVIDIA key didn't work, or `integrate.api.nvidia.com` was unreachable. Check the key at <https://build.nvidia.com/settings/api-keys>, then re-run the installer. The picker won't work until this file exists.

### "couldn't fetch claude-free-audit.py"

Same idea — a transient network or GitHub issue. Re-run the installer, or fetch manually:

```bash
curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py \
  -o ~/.local/bin/claude-free-audit.py
chmod +x ~/.local/bin/claude-free-audit.py
```

## See also

- [docs/COMMANDS.md](COMMANDS.md) — what to do once it's installed.
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — runtime errors (after install).
- [docs/FAQ.md](FAQ.md) — quick answers.
