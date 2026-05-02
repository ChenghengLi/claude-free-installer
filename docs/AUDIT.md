# Audit and calibrate — design and math

`claude-free audit` and `claude-free calibrate` are two views of the same machinery. This page covers the design, the scoring formula, the calibrate-specific optimizations, and worked examples.

If you just want to use them, [docs/COMMANDS.md](COMMANDS.md) is enough.

## TL;DR

- Use `claude-free calibrate` when you want a one-line answer to "give me the highest-quality model that responds in under a second on free NIM **right now**." It walks the catalogue top-down by code-benchmark score and writes the first model that hits the threshold to `.env`.
- Use `claude-free audit` when you want to **see** the full ranking (all measured models, three sortings) before deciding.

## Why the two paths exist

Free NVIDIA NIM has two properties that make a naive "probe everything in parallel and pick the fastest" useless:

1. **Cold-start latency dominates.** A 1.6T-param model like `deepseek-v4-pro` can take 30-90 s on the first request after a quiet period (loading weights to GPU). The same model responds in 200-500 ms once warm.
2. **The free key is rate-limited at ~40 req/min.** Probing 120 models with 3 runs each = 360 requests → 9 minutes minimum, ignoring cold starts.

So the pragmatic question isn't "which model has the lowest TTFT in the abstract" but "which good model is responsive **now**, given that I have to make these calls one at a time and there's a rate limit."

`audit` answers the abstract question (full ranking — useful when investigating). `calibrate` answers the practical question (first-fit picker — what you actually want for daily use).

## How `audit` works

```
1. Fetch /v1/models → 120-140 chat-capable models in your account.
2. Select candidates:
     --all          → all chat-capable
     --filter SUB   → only ids containing SUB
     default        → curated shortlist (BENCHMARKS dict, code-score order)
   plus any --include MODEL_ID extras. Cap at --max.
3. For each candidate, sequentially:
     - rate_limiter.wait() (default 30/min)
     - 1 warmup probe (timeout = 2.5x --timeout, capped at 90s)
     - --runs measured probes (default 3, --timeout each)
     - record median TTFT, mean tok/s
4. Look up code-benchmark score from BENCHMARKS dict.
5. Compute combined score (formula below).
6. Print three rankings: by TTFT, by code score, by combined.
7. Pick winner per --by (default: combined). Prompt to write to .env unless --no-set; --set skips the prompt.
```

Single probe = one streaming `chat/completions` call with `{"model": M, "messages": [{"role": "user", "content": "Reply with exactly the single word: pong."}], "max_tokens": 16, "temperature": 0, "stream": true}`. We measure wall-clock until the first content chunk arrives (= TTFT), then count tokens until the stream closes.

## The combined score

```
combined = code_score * exp(-TTFT_ms / tau)
```

Where:
- `code_score` is a 0-100 number from the static `BENCHMARKS` table (see [docs/BENCHMARKS.md](BENCHMARKS.md)).
- `TTFT_ms` is the median of `--runs` measured streaming probes (1 warmup discarded).
- `tau` is the **latency penalty constant** in milliseconds. Default 3000.

The shape: `exp(-TTFT/tau)` is 1.0 at TTFT=0, drops to ~0.37 at TTFT=tau, ~0.13 at 2×tau, ~0.05 at 3×tau. So with `tau=3000`:

| TTFT | Speed factor | Effect on a code-80 model |
|---|---|---|
| 100 ms | 0.97 | combined ≈ 77.4 |
| 500 ms | 0.85 | combined ≈ 67.9 |
| 1000 ms | 0.72 | combined ≈ 57.3 |
| 3000 ms | 0.37 | combined ≈ 29.4 |
| 10000 ms | 0.04 | combined ≈ 2.8 |

This is the right tradeoff for interactive coding: a 3-second TTFT is annoying but tolerable; a 10-second TTFT is unusable, so it gets nuked.

**Tuning `tau`:**

- `--tau 1500` — strict (1.5 s TTFT keeps only 37%). Use when interactivity matters most.
- `--tau 3000` — default, balanced.
- `--tau 6000` — lenient (cold models get a fairer shot). Use for batch / long-running work where a few extra seconds don't matter.

## How `calibrate` works (the early-exit walk)

`calibrate` is `audit --set --early-exit --threshold 1000` with a few extra optimizations triggered by `--early-exit`:

```
1. Same model fetch.
2. Candidate set = (all benchmarked models in your account) sorted by code_score DESC.
   --filter still works to restrict.
3. For each candidate, sequentially:
     - rate_limiter.wait()
     - 1 warmup probe (timeout = max(threshold/1000 * 5, 10s) — much smaller than audit's 90s)
     - 1 measured probe (timeout = threshold/1000 + 0.5s — tight, so a slow model is dropped fast)
     - if median TTFT <= threshold → WINNER, break out of loop.
4. If exhausted without a winner, fall back to the best combined score observed.
5. Write winner to MODEL_OPUS / SONNET / HAIKU / MODEL in .env (unless --no-set).
```

The two key differences from audit:

- **Walk order is by code score, not curated order.** This guarantees you get the best-quality model that's fast enough.
- **Measured-probe timeout = threshold + 0.5 s.** A model with 15 s TTFT gets cut off at 1.5 s instead of waiting the full `--timeout` (45 s default). Walking 7 cold huge models = ~10 s of wasted time instead of ~5 minutes.

### Why one warmup + one measurement (not three)

For `audit` you want a real distribution — 3 runs catch variance. For `calibrate` you only need a yes/no decision: "is this model fast right now?" One measurement is enough signal, and skipping the extra two saves ~3 × threshold ms per model walked.

### Why a shorter warmup budget (10 s vs 90 s)

`audit`'s warmup budget is generous because it cares about getting a real measurement out of every candidate. `calibrate`'s philosophy is "fast NOW" — a model that needs 60 s to warm up isn't fast now, by definition. Skipping it after 10 s and moving to the next is the right call.

### Fallback

If you set `--threshold 100` (sub-100 ms) on a free NIM account, nothing will pass. Calibrate then falls back to the best **combined** score observed during the walk, so `.env` always ends up with a sensible value. You'll see:

```
note: --by combined had no eligible models (missing benchmark data); falling back to TTFT.
No model met TTFT <= 100 ms. Falling back to best combined score: ...
```

## Worked example

User runs `claude-free calibrate` (defaults). The walk on a typical free NIM account produces:

```
[ 1/30] deepseek-ai/deepseek-v4-pro                  code= 80.6  timeout >1.5s
[ 2/30] minimaxai/minimax-m2.5                       code= 80.2  timeout >1.5s
[ 3/30] moonshotai/kimi-k2.6                         code= 80.2  timeout >1.5s
[ 4/30] deepseek-ai/deepseek-v4-flash                code= 79.0  timeout >1.5s
[ 5/30] minimaxai/minimax-m2.7                       code= 78.0  timeout >1.5s
[ 6/30] z-ai/glm-5.1                                 code= 78.0  timeout >1.5s
[ 7/30] z-ai/glm5                                    code= 77.8  timeout >1.5s
[ 8/30] nvidia/llama-3.3-nemotron-super-49b-v1.5     code= 76.5  no successful runs
[ 9/30] nvidia/llama-3.3-nemotron-super-49b-v1       code= 76.4  TTFT  310 ms (1 runs)  -> WINNER
```

What happened:

- The top 7 models are all huge frontier MoE / 70B+ dense models. None of them happened to be warm in NIM's cache at this moment, so each took ~10 s warmup + 1.5 s measure = ~11.5 s, then was skipped.
- `nemotron-super-49b-v1.5` is a recent enough release that NIM hasn't kept it warm — the warmup itself died.
- `nemotron-super-49b-v1` (the original v1) is **NVIDIA's house model** — they keep it warm 24/7 as a showcase. So it responded in 310 ms and won.

Total walk time: ~78 s (8 × ~11 s skips + 1 × ~12 s success). The user gets a 76.4-code-score model (within 4 points of the top of the leaderboard) that responds in 310 ms (well under the 1 s threshold).

If you want to **wait for the cold models to warm up**, run `calibrate` once to nudge them, wait a minute or two, then run it again — the previously-cold models may now be warm and qualifying.

## When to use which

| Situation | Use |
|---|---|
| First time setup, just want a good model | `claude-free calibrate` |
| Configured model feels slow today | `claude-free calibrate` |
| Want to see what's available + rankings | `claude-free audit` |
| Need to test a specific model | `claude-free audit --include nvidia_nim/specific-model --set` |
| Care more about quality than speed | `claude-free audit --by code --set` (or just edit `.env` manually) |
| Care only about latency | `claude-free audit --by ttft --set` |
| Want only Qwen / Llama / Deepseek models | `claude-free calibrate --filter qwen` etc. |

## Caveats

- **Single TTFT samples are noisy.** A model that wins one run might lose the next one — tier groups are ±10% even after 3-run medians. The combined-score formula and the early-exit threshold are both designed to be robust to this kind of noise (you don't need a precise number, you need "is this in the right ballpark").
- **Code-benchmark scores in `BENCHMARKS` are point-in-time.** Models drift, leaderboards add new versions, vendors update model cards. Run `claude-free update` periodically to pull the freshest table from `main`.
- **NIM doesn't guarantee a model stays warm** between your calibrate run and your actual `claude-free` session. The winner might have cooled by the time you start coding. If that happens, re-run calibrate.
- **TTFT is not end-to-end task time.** A model with great TTFT but slow tok/s is annoying for long generations. The current formula weights only TTFT; a future version may factor in `tok_per_s` (see [the smart_score TODO in CHANGELOG.md](../CHANGELOG.md)).

## See also

- [docs/COMMANDS.md](COMMANDS.md) — flag reference.
- [docs/BENCHMARKS.md](BENCHMARKS.md) — the static `BENCHMARKS` table, sources, and how to contribute updates.
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — what to do when audit/calibrate misbehave.
