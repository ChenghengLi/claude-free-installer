# FAQ

Short answers. For depth, follow the links.

### Is this actually free?

Yes. NVIDIA NIM gives every developer ~40 requests/minute on every available model with no credit card. `claude-free` runs Claude Code through that. You're not paying Anthropic for inference, and you're not paying NVIDIA either.

### Is it as good as paying?

For most coding work, yes. Frontier open models on NIM (`deepseek-v4-pro`, `minimax-m2.5`, `kimi-k2.6`) score 78-80% on SWE-bench Verified vs Claude Opus 4.6's 80.8% and Sonnet 4.5's 77.2%. The gap is real but small. Where you'll feel it:

- Long horizon multi-step tasks (frontier closed models are still better at staying on track).
- Code that needs deep specialized knowledge (e.g. CUDA kernel optimization).
- The fastest-responding NIM models tend to be smaller and weaker. The strongest open models are slower (cold-start, lower tok/s).

For day-to-day "fix this bug, refactor this function, write a test" work — fine.

### Is anything sent to NVIDIA / leaked?

Yes, your prompts go to NVIDIA's API. Read [NVIDIA's terms](https://build.nvidia.com/explore/discover) before using on sensitive code. Your `~/.claude/` history stays local.

### Will Anthropic ban my account for using this?

You're not signed into an Anthropic account when using `claude-free` — the binary just talks to `localhost:8082` instead of `api.anthropic.com`. No Anthropic account is involved. (If you also use Claude Code with your real Anthropic account in other terminals, that's separate and unaffected.)

### Why does Claude Code still say "Opus 4.7" when I'm running MiniMax?

Those labels are baked into the Claude Code binary and can't be relabelled. The proxy only overrides routing — the launcher prints the real model on every start, and `claude-free models` shows the current mapping. See [docs/AUDIT.md](AUDIT.md#caveats).

### `claude-free calibrate` picks model X but I want Y

Edit `~/free-claude-code/.env` directly:

```bash
MODEL_OPUS="nvidia_nim/<vendor>/<your-model>"
MODEL_SONNET="nvidia_nim/<vendor>/<your-model>"
MODEL_HAIKU="nvidia_nim/<vendor>/<your-model>"
MODEL="nvidia_nim/<vendor>/<your-model>"
```

Then `claude-free stop && claude-free`. Or use `claude-free pick` to do this interactively.

### Can I use different models per tier?

Yes — set them to different values in `.env`:

```bash
MODEL_OPUS="nvidia_nim/deepseek-ai/deepseek-v4-pro"           # smartest
MODEL_SONNET="nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1"  # default, fast
MODEL_HAIKU="nvidia_nim/qwen/qwen3-next-80b-a3b-instruct"     # cheapest/fastest
```

Now `/model` in Claude Code lets you switch between these on the fly.

### How do I get a NVIDIA API key?

<https://build.nvidia.com/settings/api-keys>. Sign in (Google / GitHub work), click "Generate API Key", copy the `nvapi-...` value. No credit card.

### Where is the rate limit set?

In `~/free-claude-code/.env`:

- `PROVIDER_RATE_LIMIT` — max requests per window (default ~35).
- `PROVIDER_RATE_WINDOW` — window size in seconds (default 60).
- `PROVIDER_MAX_CONCURRENCY` — max parallel in-flight requests.

Tune down if you keep hitting 429s, restart with `claude-free stop && claude-free`.

The audit script has its own separate rate limiter (see `--rate`); it doesn't go through the proxy.

### Does it work with Claude Code's MCP servers / hooks / slash commands?

Yes — those are all client-side features in the `claude` binary, unaffected by which backend serves the LLM responses.

### Will `/usage` show my real NIM usage?

No — Claude Code's `/usage` shows fake numbers under the proxy (it computes them from Anthropic-pricing assumptions). Use `claude-free rate` instead, which greps the actual proxy log for 429s and request counts.

### Can I use this for long-context work (>100k tokens)?

Depends on the NIM model. Most have 32k-128k context windows. Check the model card. NIM models generally don't match Claude's 200k native context, and quality often degrades sooner.

### How do I update the benchmark scores?

```bash
claude-free update
```

If you have updates to contribute, see [docs/BENCHMARKS.md#contributing-benchmark-updates](BENCHMARKS.md#contributing-benchmark-updates).

### How do I uninstall?

See [docs/INSTALL.md#uninstalling](INSTALL.md#uninstalling). TL;DR:

```bash
claude-free stop
rm -f ~/.local/bin/claude-free ~/.local/bin/claude-free-audit.py
rm -rf ~/free-claude-code
```

### Does this work in WSL?

Yes — use the **Ubuntu** installer, not the Windows one. The Ubuntu one runs natively in WSL and is simpler.

### Does this work in Docker?

Yes — bind-mount your `~/.claude` for session persistence and `~/free-claude-code/.env` (or set `NVIDIA_NIM_API_KEY` via env var) for the API key. The proxy listens on `127.0.0.1:8082`; expose / route as needed.

### What's "fast mode" and does it work here?

That's a Claude Code feature for running on a specific Anthropic model with faster output. It doesn't apply when you're routing through the NIM proxy — the model is whatever your `.env` says.

### Is there a Brew formula / apt package?

No — install is the one-shot script. PRs welcome.

### How is this different from `free-claude-code` (the upstream)?

`free-claude-code` is the proxy server. This repo (`claude-free-installer`) is **the installer + launcher + audit/calibrate workflow** that wraps it. You'd otherwise have to: install Python + uv + claude + fzf manually, clone free-claude-code, configure `.env` by hand, write your own launcher script, and figure out which model to use yourself.

## See also

- [docs/INSTALL.md](INSTALL.md) — install in detail.
- [docs/COMMANDS.md](COMMANDS.md) — every command + flag.
- [docs/AUDIT.md](AUDIT.md) — how the model picker works.
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — when something breaks.
