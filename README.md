# claude-free-installer

One-shot installer for **`claude-free`** — the official Claude Code CLI routed through the [free-claude-code](https://github.com/Alishahryar1/free-claude-code) NVIDIA NIM proxy. You get the full Claude Code experience (sessions, projects, slash commands, MCP, hooks) — answered by free NVIDIA NIM models instead of paid Anthropic models.

## Quick install

You need a free NVIDIA API key (`nvapi-...`) from <https://build.nvidia.com/settings/api-keys> first — no credit card, ~40 req/min. The installer will prompt for it.

### Ubuntu / WSL

```bash
curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free.sh -o ~/install-claude-free.sh
bash ~/install-claude-free.sh
```

### macOS (Apple Silicon and Intel)

```bash
curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-macos.sh -o ~/install-claude-free-macos.sh
bash ~/install-claude-free-macos.sh
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 | iex
```

If PowerShell complains about execution policy, run once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.

After install, open a **new** terminal so PATH refreshes and run:

```bash
claude-free
```

> Already installed and want to upgrade? See [docs/INSTALL.md#updating-an-existing-install](docs/INSTALL.md#updating-an-existing-install).

## What you get

- A `claude-free` launcher at `~/.local/bin/claude-free` with the subcommands listed below.
- The `free-claude-code` proxy at `~/free-claude-code/`, configured with `MODEL_OPUS = MODEL_SONNET = MODEL_HAIKU = MODEL = nvidia_nim/minimaxai/minimax-m2.5` by default.
- The audit script at `~/.local/bin/claude-free-audit.py` for ranking and switching models.
- Sessions and history shared with native `claude` (both binaries read `~/.claude/`).

## Commands at a glance

| Command | What it does |
|---|---|
| `claude-free` | Start proxy if needed, launch Claude Code |
| `claude-free pick` | Interactive NIM model picker (fzf), then launch |
| `claude-free audit` | Probe NIM chat models for TTFT + code-benchmark score, print three rankings |
| `claude-free calibrate` | Walk models top-down by code score, pick the first one with TTFT ≤ 1 s, write to `.env` |
| `claude-free update` | Refresh the audit script + benchmarks table from GitHub |
| `claude-free models` / `status` | Show current `/model` tier mapping + proxy status |
| `claude-free rate` | Show NVIDIA rate-limit hits from proxy log |
| `claude-free logs` | Tail the proxy log |
| `claude-free stop` | Kill the proxy |
| `claude-free help` | Full help with all flags |

Detailed reference for every command and flag: [docs/COMMANDS.md](docs/COMMANDS.md).

## Picking a fast + good model

```bash
claude-free calibrate              # most users want this — picks the best model that responds in <1s
claude-free calibrate --threshold 500    # be stricter
claude-free calibrate --threshold 2000   # be lenient
claude-free audit                  # see the full ranking instead of auto-picking
```

`calibrate` walks every benchmarked model in your account in **code-score-descending** order, sends a tiny streaming chat request to each, and stops at the first one that responds within the threshold. The winner is written to all four `MODEL_*` keys in `~/free-claude-code/.env`. The whole walk is rate-limited (default 30 req/min, free NIM is ~40/min) and uses a dynamic per-probe timeout so slow cold models are skipped after ~1.5 s instead of waiting the full 30 s.

Read the full design — the math, why early-exit, when to use audit vs calibrate, examples — in [docs/AUDIT.md](docs/AUDIT.md).

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — per-OS install in detail, what files end up where, how to upgrade or uninstall, install-time errors
- [docs/COMMANDS.md](docs/COMMANDS.md) — reference for every subcommand and every flag
- [docs/AUDIT.md](docs/AUDIT.md) — deep dive on `audit` / `calibrate`, the scoring formula, when to use what
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — the benchmark table, sources, methodology, how to submit updates
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — runtime issues: 429s, cold starts, proxy crashes, .env confusion
- [docs/FAQ.md](docs/FAQ.md) — short answers to common questions
- [CHANGELOG.md](CHANGELOG.md) — what changed in each commit

## Notes

- **Claude Code's `/model` dialog still shows "Opus 4.7", "Sonnet 4.6", "Haiku 4.5"** — those names are baked into the binary. Only the routing is overridden. `claude-free models` shows the real NVIDIA model behind each tier.
- Free NVIDIA NIM is occasionally flaky — on a 502 / timeout / cold-start, switch with `claude-free pick` or re-run `claude-free calibrate`.
- WSL users — use the Ubuntu installer, not the Windows one. It's simpler.
