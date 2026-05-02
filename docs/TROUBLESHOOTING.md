# Troubleshooting

Runtime issues — things that go wrong **after** install. For install-time errors see [docs/INSTALL.md#install-time-errors](INSTALL.md#install-time-errors).

## Quick triage

```
claude-free status        # is the proxy running? what model is set?
claude-free rate          # any 429s in the log?
claude-free logs          # what is the proxy actually doing?
```

99% of issues fall into one of these buckets:
- Rate limit hits → see [Rate limits](#rate-limits-429).
- Model isn't responding → see [Cold-start timeouts](#cold-start-timeouts) or [Model not provisioned](#model-not-provisioned-404).
- Proxy died → see [Proxy won't start / dies](#proxy-wont-start--dies-immediately).
- Tier mapping wrong → see [Wrong model is being used](#wrong-model-is-being-used-tier-mapping-confusion).

## Rate limits (429)

**Symptom:** Claude Code spits out empty responses or `RateLimitError` messages, `claude-free rate` shows non-zero `rate-limit (429) hits`.

**Why:** Free NVIDIA NIM caps each key at ~40 requests/minute. The proxy tries to throttle to that, but agentic workflows (like Claude Code's tool-use loop) burst — a single user message can trigger 5-10 model calls.

**Fixes** (in order of effort):

1. Slow down: edit `~/free-claude-code/.env` and set `PROVIDER_RATE_LIMIT=30` (or lower). Then `claude-free stop && claude-free`. The proxy will queue requests instead of letting them all hit NIM at once.
2. Switch to a less-popular model — heavily-used models tend to throttle harder. Try `claude-free pick` and pick something off-meta.
3. If you're running `claude-free calibrate` in parallel with a `claude-free` session, you're sharing the rate budget. Don't.
4. Get a second NVIDIA key (free, just need a different email) and rotate manually.

## Cold-start timeouts

**Symptom:** A model that "should be fast" takes 30-90 s on the first response, or `claude-free calibrate` skips a frontier model with `timeout >1.5s`.

**Why:** NVIDIA NIM evicts unused models from GPU. The first request to a cold model has to load weights — for a 1T-param MoE that's 20-60 s.

**Fixes:**

1. **Just send another request.** The first prompt warms the model. Subsequent requests are sub-second.
2. **Re-run `claude-free calibrate` later.** A model that timed out on this walk may be warm in 2 minutes.
3. **Pick a model NVIDIA keeps warm.** Their house models (`nvidia/llama-3.3-nemotron-super-49b-v1`, smaller Qwen MoE variants) are kept resident 24/7 as showcases — they almost never cold-start.
4. **If you're patient, give cold models more budget:** `claude-free audit --include nvidia_nim/deepseek-ai/deepseek-v4-pro --timeout 120`. The audit's `--timeout` becomes the warmup budget (capped at 90 s by default; explicitly setting it past that lifts the cap).

## Model not provisioned (404)

**Symptom:** `claude-free audit` reports `HTTP 404 {"detail":"Function '...' Not found for account '...'"}` for one or more models.

**Why:** NIM lists models in `/v1/models` that aren't actually provisioned for your account. This is normal — different accounts get different model access.

**Fix:** Nothing to do. The audit script logs and skips. If you specifically need the model, contact NVIDIA developer support to request provisioning, or pick a different one.

## Proxy won't start / dies immediately

**Symptom:** `claude-free` prints "proxy died during startup" with a tail of the log; or `claude-free status` always shows "proxy not running".

**Diagnosis:**

```bash
claude-free logs               # tail the log
cat ~/free-claude-code/.env    # is NVIDIA_NIM_API_KEY actually set?
ls ~/free-claude-code/         # is the repo even there?
cd ~/free-claude-code && uv sync   # python deps OK?
```

**Common causes:**

- **Port 8082 already in use** by another process. Find it: `lsof -i :8082` (Linux/macOS) or `Get-NetTCPConnection -LocalPort 8082` (Windows). Kill it or change `PORT` at the top of `~/.local/bin/claude-free`.
- **`uv sync` failed** — usually a transient network issue. Run `cd ~/free-claude-code && uv sync` manually and check the error.
- **NVIDIA key expired / revoked.** Get a new one at <https://build.nvidia.com/settings/api-keys>, edit `NVIDIA_NIM_API_KEY=` in `.env`, restart.
- **Python interpreter version mismatch.** The proxy expects Python 3.14 (installed by `uv python install 3.14`). If you have something else pinned, run `cd ~/free-claude-code && uv python install 3.14 && uv sync` and try again.

## Wrong model is being used (tier mapping confusion)

**Symptom:** Claude Code shows "Opus 4.7" but the responses look like a small model, or vice versa.

**Why:** Claude Code's `/model` dialog shows hardcoded labels — they cannot be relabelled. Only the *routing* is overridden by the proxy. So "Opus 4.7" might be running `nvidia_nim/meta/llama-3.1-8b-instruct` if your `MODEL_OPUS` is set there.

**Diagnosis:**

```bash
claude-free models     # shows what each tier actually maps to
```

**Fix:** Edit `~/free-claude-code/.env` and set `MODEL_OPUS / MODEL_SONNET / MODEL_HAIKU / MODEL` to whatever you want. Or just `claude-free calibrate` to auto-pick. Restart the proxy: `claude-free stop && claude-free`.

## Picker (`claude-free pick`) is empty / hangs

**Symptom:** fzf opens with no entries, or hangs.

**Diagnosis:**

```bash
ls -la ~/free-claude-code/nvidia_nim_models.json    # exists? non-zero?
which fzf                                            # on PATH?
```

**Fixes:**

- Empty / missing `nvidia_nim_models.json`: re-fetch it.
  ```bash
  curl -fsSL "https://integrate.api.nvidia.com/v1/models" \
    -H "Authorization: Bearer $(grep NVIDIA_NIM_API_KEY ~/free-claude-code/.env | sed 's/.*="\(.*\)"/\1/')" \
    -o ~/free-claude-code/nvidia_nim_models.json
  ```
- `fzf` missing: `~/.local/bin/fzf` deleted somehow. Re-run the installer (it's idempotent and will reinstall fzf only).

## `claude-free` keeps prompting "Reuse it?" for the API key

**Symptom:** Every install re-prompts about the saved key.

**Why:** The installer's "found existing key" prompt defaults to `Y`. Just press enter.

If you want to fully skip the prompt in CI / scripted setups, set `NVAPI_KEY` before running:

```bash
NVAPI_KEY=nvapi-... bash ~/install-claude-free.sh
```

The installer reads it from the environment if present.

## `claude-free update` says "fetch failed"

**Symptom:**

```
claude-free update -- refreshing audit script + benchmarks table
  fetching https://raw.githubusercontent.com/.../claude-free-audit.py
fetch failed -- keeping existing script
```

**Why:** GitHub raw is unreachable, or the URL changed.

**Fixes:**

- Confirm GitHub is up: `curl -I https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py`
- Check your network blocks `raw.githubusercontent.com` (some corporate proxies do).
- Manually fetch: download the file from <https://github.com/ChenghengLi/claude-free-installer/blob/main/claude-free-audit.py> and place it at `~/.local/bin/claude-free-audit.py` (Linux/macOS) or `$HOME\.local\bin\claude-free-audit.py` (Windows).

## `python: command not found` when running audit

**Symptom:** `claude-free audit` exits with a Python-not-found error.

**Why:** Linux/macOS launchers call `python3`; Windows launcher tries `python` then `python3`. If neither is on PATH, audit can't run.

**Fix:** Install Python 3 and ensure it's on PATH. Re-run the installer if needed.

## Audit shows `code = n/a` for all models

**Symptom:** Every audit row shows `n/a` in the CODE column.

**Why:** Your `claude-free-audit.py` is older than the BENCHMARKS table refresh, or you somehow have a corrupted file with an empty BENCHMARKS dict.

**Fix:**

```bash
claude-free update
```

## Sessions / chat history disappeared

**Symptom:** Past conversations are missing.

**Why:** Sessions live at `~/.claude/`. They're shared with native `claude` and survive `claude-free` reinstalls. If they're missing:

- You ran `rm -rf ~/.claude` (manually or as part of an uninstall).
- A different user account is being used.
- The Claude Code update changed the storage layout (rare).

**Fix:** Check `~/.claude/projects/` — sessions are organized by project directory.

## Still stuck

Open an issue at <https://github.com/ChenghengLi/claude-free-installer/issues> with:

- OS + version (`uname -a` / `Get-ComputerInfo`)
- The output of `claude-free status`
- The last 30 lines of `claude-free logs`
- The exact command + error you're hitting

## See also

- [docs/INSTALL.md](INSTALL.md) — install-time errors.
- [docs/COMMANDS.md](COMMANDS.md) — all subcommands and flags.
- [docs/AUDIT.md](AUDIT.md) — why calibrate skips cold models.
