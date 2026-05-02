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
  - `claude-free audit` — probe NVIDIA NIM models for latency + code-benchmark score, print rankings
  - `claude-free calibrate` — walk models top-down by code score, pick the first one with TTFT ≤ 1 s, write it to `.env`
  - `claude-free update` — refresh `~/.local/bin/claude-free-audit.py` from GitHub (get new models + updated benchmark scores without re-running the installer)
  - `claude-free models` — show current `/model` tier mapping
  - `claude-free rate` — NVIDIA rate-limit hits (replaces `/usage`)
  - `claude-free logs` / `status` / `stop` / `help`

## Default model mapping

Every Claude Code `/model` tier (Opus / Sonnet / Haiku / fallback) routes to **MiniMax M2.5** by default — 80.2% on SWE-bench Verified (matches Claude Opus 4.6) and ~0.5s latency on NVIDIA NIM. Edit `~/free-claude-code/.env` to change tiers, or run `claude-free calibrate` to let the script choose.

## Picking a model: `audit` and `calibrate`

NVIDIA exposes ~140 models on the free tier; not all are provisioned for every account, and latency varies wildly (≈400 ms for some 8x22B Mixtral runs, ≈90 s on a cold Llama 405B). `claude-free audit` ranks them so you don't have to guess.

```bash
claude-free audit              # probe a curated shortlist, print rankings
claude-free audit --all        # probe every chat-capable model in your account
claude-free audit --filter llama   # only ids containing "llama"
claude-free audit --runs 5         # 5 measured runs per model (default 3, after 1 warmup)
claude-free audit --by ttft        # rank winner purely by lowest TTFT
claude-free audit --by code        # rank winner by code-benchmark score
claude-free audit --tau 1500       # penalize latency harder (default tau=3000ms)
claude-free audit --rate 20        # cap requests at 20/min (default 30; free NIM ~40/min)
claude-free audit --set            # auto-write the winner to .env without prompting

claude-free calibrate            # = audit --set --early-exit --threshold 1000
claude-free calibrate --threshold 500    # be stricter — require sub-500 ms
claude-free calibrate --threshold 2000   # be lenient — accept up to 2 s
claude-free calibrate --filter qwen      # only consider Qwen models
claude-free calibrate --rate 20          # gentler on the rate limit

claude-free update             # pull the latest audit script + benchmarks table
```

### Rate limiting

Free NVIDIA NIM caps each key at roughly **40 requests/minute**. The audit script respects this with a built-in sliding-window limiter (default 30/min — leaves headroom for the proxy). On a `429`, it honours the `Retry-After` header and retries once. Tune with `--rate REQ_PER_MIN`, or set `--rate 0` to disable.

## Updating an existing install

You have two upgrade paths depending on what changed.

**Just refresh the benchmarks table / audit script** (most common — vendor benchmarks update, the BENCHMARKS dict in `claude-free-audit.py` gets a new entry):

```bash
claude-free update
```

That fetches `claude-free-audit.py` from `raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py` and atomically replaces `~/.local/bin/claude-free-audit.py`. No re-install, no shell restart needed. Run `claude-free calibrate` afterwards if you want to re-pick the winner with the new scores.

**Upgrade everything** (launcher gained a new subcommand, install script changed, your old install pre-dates `claude-free audit`/`calibrate`/`update`):

Re-run the installer for your platform — it's idempotent and skips steps that are already done, but always rewrites the launcher and audit script with the latest version.

```bash
# Ubuntu / WSL
bash <(curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free.sh)

# macOS
bash <(curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-macos.sh)

# Windows (PowerShell)
irm https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/install-claude-free-windows.ps1 | iex
```

Re-running the installer keeps your existing `~/free-claude-code/.env` (it'll prompt before reusing the saved API key), so your model tier mappings survive the upgrade.

**Check what version you're on** (handy for bug reports):

```bash
head -3 ~/.local/bin/claude-free-audit.py     # Linux/macOS
type %USERPROFILE%\.local\bin\claude-free-audit.py | more     # Windows cmd
Get-Content $HOME\.local\bin\claude-free-audit.py -TotalCount 3   # Windows PowerShell
```

The first three lines include a comment with the script's purpose; the BENCHMARKS dict has a `Last refreshed:` date you can grep for:

```bash
grep "Last refreshed" ~/.local/bin/claude-free-audit.py
```

For each model the audit sends one tiny streaming chat completion (`max_tokens=16`) and measures **time-to-first-token (TTFT)**.

**`audit`** runs every candidate, then ranks them three ways: lowest TTFT, best code score, and a combined "fast+good" score:

```
combined = code_score * exp(-TTFT_ms / tau)      # tau defaults to 3000 ms
```

So a 1-second TTFT keeps ~72% of a model's quality score, a 3-second TTFT keeps ~37%, and a 10-second TTFT keeps ~3%.

**`calibrate`** is the smarter, faster alternative. It walks **every benchmarked model in your account in code-score-descending order** (best models first) and sends one warmup + one measured probe to each. The **first** model whose TTFT is `<=` the threshold (default 1000 ms) wins — calibrate stops probing the rest, writes the winner to `MODEL_OPUS / MODEL_SONNET / MODEL_HAIKU / MODEL` in `~/free-claude-code/.env`, and exits. If nothing meets the threshold, it falls back to the best combined score it observed.

This matches what you actually want at 9am on Monday: "give me the highest-quality model that responds in under a second on free NIM right now."

After calibrating, restart any running proxy: `claude-free stop && claude-free`.

> Note: free NIM cold-starts huge models (deepseek-v4-pro, minimax-m2.7, kimi-k2.6) at 30–90 s. The script gives the warmup probe 2.5x the measured-run timeout, but if the model still isn't loaded after that, calibrate moves on. Run calibrate again later — once the model is warm in NIM's cache, it'll usually clear the threshold.

> Benchmark scores in the audit are baked into `claude-free-audit.py` (a static table, ASCII-only stdlib script). They reflect public leaderboards as of late 2025 / early 2026; some are estimates and labelled `SRC=estimate` in the output. PRs welcome.

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
