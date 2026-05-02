# Commands reference

Every `claude-free` subcommand with synopsis, description, flags, exit codes, and examples.

## Overview

```
claude-free [args...]      start proxy if needed, launch claude (passes args through)
claude-free pick           interactive NIM model picker (fzf), then launch
claude-free audit          probe NIM chat models for TTFT + code benchmarks
claude-free calibrate      walk by code-score, pick first with TTFT <= 1s, set .env
claude-free update         refresh ~/.local/bin/claude-free-audit.py from GitHub
claude-free models         show /model tier mapping + proxy status
claude-free status         alias for `models`
claude-free rate           show NVIDIA rate-limit hits from proxy log
claude-free logs           tail the proxy log
claude-free stop           kill the running proxy
claude-free help           print full help
```

---

## `claude-free` (default — launch Claude Code)

**Synopsis**

```
claude-free [args...]
```

Starts the `free-claude-code` proxy on `127.0.0.1:8082` if it isn't already up, sets `ANTHROPIC_BASE_URL=http://localhost:8082` and `ANTHROPIC_AUTH_TOKEN=freecc`, then `exec`s `claude` with any additional args. So:

```bash
claude-free                     # plain claude session
claude-free --resume            # resume the last session
claude-free --print "hello"     # one-shot non-interactive
claude-free /init               # use Claude Code's slash commands
```

The proxy stays running across `claude` invocations — it only dies when you call `claude-free stop` or kill the process tree.

**What's printed on launch**

```
claude-free via NVIDIA NIM (free) — /model tiers route to:
  Opus   -> nvidia_nim/minimaxai/minimax-m2.5
  Sonnet -> nvidia_nim/minimaxai/minimax-m2.5  (default)
  Haiku  -> nvidia_nim/minimaxai/minimax-m2.5
```

**Exit codes**

- Whatever `claude` exits with.
- `1` if the proxy failed to start in 20 s — tail of `~/free-claude-code/claude-free-proxy.log` is printed.

---

## `claude-free pick`

**Synopsis**

```
claude-free pick [pick-args...]
```

Opens the upstream `claude-pick` interactive picker (built on [fzf](https://github.com/junegunn/fzf)) with the full NVIDIA NIM catalogue. Selecting a model writes it to `MODEL_OPUS / SONNET / HAIKU / MODEL` in `.env`, then launches `claude`.

Use this when you know exactly which model you want and don't need the audit / calibrate workflow.

---

## `claude-free audit`

**Synopsis**

```
claude-free audit [flags...]
```

Sends a tiny streaming chat completion (`max_tokens=16`) to each candidate model, measures **time-to-first-token (TTFT)**, and prints three rankings: by lowest TTFT, by code-benchmark score, and by combined "fast + good" score.

By default, audit walks a curated list of frontier-tier models that are present in your account. Use `--all`, `--filter`, or `--include` to expand the set.

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--all` | off | Probe every chat-capable model in your account (~120 models) |
| `--filter SUBSTR` | — | Only probe model ids containing `SUBSTR` (case-insensitive) |
| `--include MODEL_ID` | — | Add a specific model id to the candidate list (repeatable) |
| `--runs N` | 3 | Measured runs per model after 1 warmup |
| `--no-warmup` | off | Skip the warmup probe (faster but cold models will time out) |
| `--timeout SECS` | 45 | Per-probe timeout (warmup gets 2.5x this) |
| `--max N` | 15 | Max number of models to probe |
| `--by {combined,ttft,code}` | combined | Which ranking decides the winner |
| `--tau MS` | 3000 | Latency penalty constant — at TTFT=tau, you keep ~37% of the model's quality score |
| `--rate REQ_PER_MIN` | 30 | Sliding-window rate limit (free NIM is ~40/min). 0 = no limit |
| `--early-exit` | off | Switch to quality-priority walk and stop at first model with TTFT ≤ `--threshold` |
| `--threshold MS` | 0 (off) | TTFT threshold for `--early-exit` (default 1000 when `--early-exit` is on) |
| `--set` | off | Auto-write the winner to `.env` without prompting |
| `--no-set` | off | Never offer to write the winner |
| `--key KEY` | — | NVIDIA API key (overrides env / `.env`) |
| `--env-file PATH` | `~/free-claude-code/.env` | Where to write the winner |

**Examples**

```bash
# Default: probe a curated shortlist, print three rankings, prompt to set the winner
claude-free audit

# Probe every Llama model in your account, 5 measured runs each
claude-free audit --filter llama --runs 5

# Probe everything chat-capable (~120 models). Takes a while.
claude-free audit --all

# Auto-set the winner without prompting, ranked by lowest TTFT only
claude-free audit --set --by ttft

# Penalize latency harder — 1.5s tau means a 1.5s TTFT keeps ~37% of the code score
claude-free audit --tau 1500
```

See [docs/AUDIT.md](AUDIT.md) for the math behind the combined score and worked examples.

**Exit codes**

- `0` on success.
- `1` if no candidates matched, no probes succeeded, or `.env` is missing on `--set`.
- `2` on bad flags.

---

## `claude-free calibrate`

**Synopsis**

```
claude-free calibrate [flags...]
```

The "just pick me a fast good one and write it to .env" command. Internally:

```
claude-free-audit.py --set --early-exit --threshold 1000  [your extra flags]
```

So `calibrate` walks **every benchmarked model in your account** in code-score-descending order, sends `1 warmup + 1 measured` request to each, and stops at the **first** model whose TTFT is ≤ 1000 ms. That model is written to all four `MODEL_*` keys in `~/free-claude-code/.env`.

**Tweakable defaults**

```bash
claude-free calibrate --threshold 500      # be stricter (sub-500 ms only)
claude-free calibrate --threshold 2000     # be lenient (up to 2 s)
claude-free calibrate --filter qwen        # only consider Qwen models
claude-free calibrate --rate 20            # gentler on the rate limit
claude-free calibrate --no-warmup          # skip warmup (very fast, but cold models won't get a fair shot)
```

**What you'll see**

```
claude-free audit  -- ranking NVIDIA NIM chat models by TTFT and code benchmarks

  rate limit: 30 req/min sliding window (sleep before bursts)
  fetching model catalogue from https://integrate.api.nvidia.com/v1/models ... 134 models
  walking 30 benchmarked model(s) by code-score desc, first one with TTFT <= 1000 ms wins
  per-probe timeout: warmup 10s, measured 1.5s, 1 measured run/model

  [ 1/30] deepseek-ai/deepseek-v4-pro                  code= 80.6  timeout >1.5s
  [ 2/30] minimaxai/minimax-m2.5                       code= 80.2  timeout >1.5s
  [ 3/30] moonshotai/kimi-k2.6                         code= 80.2  timeout >1.5s
  ...
  [ 9/30] nvidia/llama-3.3-nemotron-super-49b-v1       code= 76.4  TTFT  310 ms (1 runs)  -> WINNER

Picked: nvidia/llama-3.3-nemotron-super-49b-v1  (TTFT 310 ms, code 76.4, src swebench)
  -> nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
Updated /home/.../free-claude-code/.env.
Restart any running proxy: `claude-free stop && claude-free` to pick up the new tier mapping.
```

If nothing meets the threshold, calibrate falls back to the best **combined score** it observed — so you always end up with *something* set.

**Exit codes** — same as `audit`.

---

## `claude-free update`

**Synopsis**

```
claude-free update
```

Atomically replaces `~/.local/bin/claude-free-audit.py` with the latest version from `https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py`. Use this when:

- The benchmarks table has been refreshed (new models, updated SWE-bench scores).
- The audit script gained a new flag.
- A bug was fixed.

This **does not** update the `claude-free` launcher itself — for that, re-run the installer (see [docs/INSTALL.md#updating-an-existing-install](INSTALL.md#updating-an-existing-install)).

**Examples**

```bash
claude-free update                              # fetch from main, overwrite local
claude-free update && claude-free calibrate     # update then re-pick
```

**Exit codes**

- `0` on success.
- `1` on fetch failure (existing script is preserved).

---

## `claude-free models` / `claude-free status`

**Synopsis**

```
claude-free models
claude-free status
```

Prints whether the proxy is running and the current `/model` tier mapping:

```
proxy up on :8082
  pid: 12345

/model tier mapping (what each Claude Code label actually runs):
  Opus      (label: 'Opus 4.7')   -> nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
  Sonnet    (label: 'Sonnet 4.6') -> nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
  Haiku     (label: 'Haiku 4.5')  -> nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
  Fallback  (MODEL=)              -> nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1
```

Read directly from `~/free-claude-code/.env` — no proxy required.

---

## `claude-free rate`

**Synopsis**

```
claude-free rate
```

Greps the proxy log for HTTP 429 / rate-limit / 5xx hits and shows counts plus the last 5 rate-limit lines. Replaces Claude Code's `/usage` (which shows fake numbers under the proxy).

```
log lines             : 2483
request lines         : 412
rate-limit (429) hits : 7
5xx errors            : 2

last 5 rate-limit lines:
  ...

configured proxy throttle (.env):
  PROVIDER_RATE_LIMIT      = 35
  PROVIDER_RATE_WINDOW     = 60
  PROVIDER_MAX_CONCURRENCY = 4
```

If you're seeing 429s, lower `PROVIDER_RATE_LIMIT` in `.env` and `claude-free stop && claude-free` to restart the proxy.

---

## `claude-free logs`

```
claude-free logs
```

`tail -f` on `~/free-claude-code/claude-free-proxy.log`. Ctrl-C to exit.

---

## `claude-free stop`

```
claude-free stop
```

Kills the proxy by PID (from `~/free-claude-code/claude-free-proxy.pid`), then `pkill`s any stragglers matching `uvicorn server:app.*--port 8082`.

---

## `claude-free help`

Prints the full help text. The launcher itself ignores `-h` / `--help` because those are forwarded to `claude` for its own help — use `help` (no dashes) or `--help-claude-free`.

---

## Internal: `claude-free-audit.py`

The audit / calibrate / update commands all delegate to `~/.local/bin/claude-free-audit.py`. You can run it directly if you want full control:

```bash
python3 ~/.local/bin/claude-free-audit.py --help
python3 ~/.local/bin/claude-free-audit.py --early-exit --threshold 800 --set
```

The script reads the NVIDIA key from `$NVIDIA_NIM_API_KEY` → `$NVIDIA_API_KEY` → `~/free-claude-code/.env` in that order, so you can run it standalone outside the launcher's environment.

## See also

- [docs/AUDIT.md](AUDIT.md) — design and math behind audit/calibrate.
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — what to do when commands fail at runtime.
