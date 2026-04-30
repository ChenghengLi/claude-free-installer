# claude-free-installer

One-shot installer for **`claude-free`** — the official Claude Code CLI routed through the [free-claude-code](https://github.com/Alishahryar1/free-claude-code) NVIDIA NIM proxy.

You get the full native Claude Code experience (sessions, history, projects, slash commands, MCP, hooks) — answered by free NVIDIA NIM models instead of paid Anthropic models.

## What it sets up

- [`uv`](https://github.com/astral-sh/uv) (Python package manager) + Python 3.14
- [Claude Code](https://claude.ai/code)
- [`fzf`](https://github.com/junegunn/fzf) (for the interactive model picker)
- [`free-claude-code`](https://github.com/Alishahryar1/free-claude-code) cloned at `~/free-claude-code`
- A `claude-free` launcher at `~/.local/bin/claude-free` with subcommands:
  - `claude-free` — start proxy + launch Claude Code
  - `claude-free pick` — interactive NVIDIA model picker (fzf)
  - `claude-free models` — show current `/model` tier mapping
  - `claude-free rate` — NVIDIA rate-limit hits (replaces `/usage`)
  - `claude-free logs` / `status` / `stop` / `help`

## Default model mapping

Every Claude Code `/model` tier (Opus / Sonnet / Haiku / fallback) routes to **MiniMax M2.5** by default — 80.2% on SWE-bench Verified (matches Claude Opus 4.6) and ~0.5s latency on NVIDIA NIM. Edit `~/free-claude-code/.env` to change tiers.

## Prerequisites

A free **NVIDIA API key** (`nvapi-...`) from <https://build.nvidia.com/settings/api-keys>. No credit card required, ~40 req/min rate limit.

## Install

### Ubuntu / WSL

```bash
curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free.sh -o ~/install-claude-free.sh
bash ~/install-claude-free.sh
```

### macOS (Apple Silicon M-series **and** Intel)

Same script auto-detects your arch.

```bash
curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-macos.sh -o ~/install-claude-free-macos.sh
bash ~/install-claude-free-macos.sh
```

The installer will prompt you for the NVIDIA API key once, then handle everything else. It is **idempotent** — re-running skips already-completed steps.

After install, open a new shell (or `source ~/.bashrc` / `~/.zshrc`) and run:

```bash
claude-free
```

### Windows (PowerShell)

Open a PowerShell window and run:

```powershell
irm https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 | iex
```

Prerequisites: [Git for Windows](https://git-scm.com/download/win) and [Python 3](https://www.python.org/downloads/windows/) (with "Add to PATH" ticked).

If PowerShell complains about execution policy, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

After install, open a **new** terminal so PATH refreshes, then:

```powershell
claude-free
```

(WSL users — use the Ubuntu installer instead, it's simpler.)

## Notes

- **The `/model` dialog inside Claude Code still shows "Opus 4.7", "Sonnet 4.6", "Haiku 4.5"** — those names are baked into the Claude Code binary and cannot be relabeled. Only the routing is overridden. The launcher prints the real NVIDIA model on every start; `claude-free models` shows the current mapping.
- **Sessions and history are shared with native `claude`** because both binaries read `~/.claude/`. You can resume a chat started in either.
- Free NVIDIA NIM hosted infra is occasionally flaky — if a model 502s or times out, switch with `claude-free pick`.
