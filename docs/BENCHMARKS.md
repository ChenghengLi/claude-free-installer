# Benchmarks table — sources, methodology, contributing updates

The `BENCHMARKS` dict in [`claude-free-audit.py`](../claude-free-audit.py) holds a static code-benchmark score for every model the audit/calibrate flow knows about. This page documents what's in it, where the numbers come from, and how to contribute updates.

## Why a static table at all?

The alternatives were:
- **Live-fetch from a leaderboard API.** No public, stable, machine-readable leaderboard exists that covers all NIM models. swebench.com has scores but no API; livecodebench has a JSON file but limited coverage; vendor model cards are HTML.
- **Don't track quality at all, just rank by latency.** That's what `audit --by ttft` does, but it picks `meta/llama-3.1-8b-instruct` (12 code score, 300 ms TTFT) over `nvidia/llama-3.3-nemotron-super-49b-v1` (76 code score, 310 ms TTFT). Useless for actual coding work.

So the table is curated, with `claude-free update` as the upgrade path for refreshing it without re-installing.

## The methodology

For each model:

1. **Pick the best available benchmark.** Source priority:
   1. **SWE-bench Verified** — the most relevant for agentic coding (Claude Code's job). 500 hand-verified GitHub issues, the model has to produce a working patch.
   2. **LiveCodeBench** — algorithmic / competitive programming. Continuously updated, contamination-resistant.
   3. **HumanEval** — short single-function generation. Saturated, no longer differentiates frontier models, but useful for older or smaller models.
2. **Set `code_score` to that benchmark's percentage.** Sometimes adjusted slightly when there's strong cross-benchmark disagreement (e.g. a model with HumanEval 92 but LCB 25 gets a code_score closer to LCB).
3. **Tag the source:** `swebench`, `livecodebench`, `humaneval`, or `estimate`.

Estimates are used when the vendor hasn't published a SWE-bench Verified score and no third-party leaderboard has measured it. They're best-effort interpolations from related benchmarks (SWE-Pro, MultiSWE, vendor-claimed agentic scores). The `src` field flags them so the audit display can warn the user.

## The current table (May 2026 snapshot)

The full table is in `claude-free-audit.py`. Here's the same data sorted by `code_score`:

### Frontier (≥ 76)

| Model | Code score | Source | Notes |
|---|---|---|---|
| deepseek-ai/deepseek-v4-pro | 80.6 | swebench | 1.6T MoE, current open-source SWE-V leader |
| minimaxai/minimax-m2.5 | 80.2 | swebench | the small-model champ |
| moonshotai/kimi-k2.6 | 80.2 | swebench | confirmed mid-2026 |
| deepseek-ai/deepseek-v4-flash | 79.0 | swebench | smaller v4 variant |
| minimaxai/minimax-m2.7 | 78.0 | swebench | newer than m2.5 but slightly lower SWE-V |
| z-ai/glm-5.1 | 78.0 | estimate | |
| z-ai/glm5 | 77.8 | swebench | |
| nvidia/llama-3.3-nemotron-super-49b-v1.5 | 76.5 | estimate | |
| qwen/qwen3.5-397b-a17b | 76.4 | swebench | |
| nvidia/llama-3.3-nemotron-super-49b-v1 | 76.4 | swebench | NVIDIA's house model — kept warm 24/7 |

### Strong (60-75)

| Model | Code score | Source |
|---|---|---|
| moonshotai/kimi-k2-instruct-0905 | 73.0 | estimate |
| mistralai/devstral-2-123b-instruct-2512 | 72.2 | swebench |
| moonshotai/kimi-k2-thinking | 71.0 | estimate |
| qwen/qwen3-coder-480b-a35b-instruct | 70.0 | swebench |
| moonshotai/kimi-k2-instruct | 70.0 | estimate |
| qwen/qwen3.5-122b-a10b | 70.0 | estimate |
| z-ai/glm4.7 | 70.0 | estimate |
| nvidia/llama-3.1-nemotron-ultra-253b-v1 | 68.0 | estimate |
| deepseek-ai/deepseek-v3.2 | 67.8 | swebench |
| deepseek-ai/deepseek-v3 | 67.8 | swebench |
| deepseek-ai/deepseek-v3.1-terminus | 62.0 | estimate |
| nvidia/nemotron-3-super-120b-a12b | 60.5 | swebench |

### Mid (35-60)

| Model | Code score | Source |
|---|---|---|
| mistralai/mistral-large-3-675b-instruct-2512 | 58.0 | estimate |
| meta/llama-4-maverick-17b-128e-instruct | 55.0 | estimate |
| qwen/qwen2.5-72b-instruct | 50.0 | livecodebench |
| qwen/qwen3-next-80b-a3b-thinking | 50.0 | estimate |
| qwen/qwen2.5-coder-32b-instruct | 50.0 | estimate |
| deepseek-ai/deepseek-r1 | 49.2 | swebench |
| mistralai/mistral-medium-3.5-128b | 45.0 | estimate |
| meta/llama-3.1-405b-instruct | 45.0 | estimate |
| mistralai/mistral-medium-3-instruct | 40.0 | estimate |

### Lower / fast tier (≤ 35)

| Model | Code score | Source |
|---|---|---|
| meta/llama-3.3-70b-instruct | 30.0 | estimate |
| mistralai/mistral-large-2-instruct | 32.0 | estimate |
| qwen/qwen3-next-80b-a3b-instruct | 30.0 | swebench |
| openai/gpt-oss-120b | 30.0 | swebench |
| nvidia/llama-3.1-nemotron-70b-instruct | 30.0 | estimate |
| 01-ai/yi-large | 28.0 | estimate |
| meta/llama-3.1-70b-instruct | 25.0 | estimate |
| google/gemma-3-27b-it | 25.0 | estimate |
| mistralai/mixtral-8x22b-instruct-v0.1 | 22.0 | estimate |
| google/gemma-2-27b-it | 18.0 | estimate |
| openai/gpt-oss-20b | 15.0 | estimate |
| meta/llama-3.1-8b-instruct | 12.0 | estimate |

## Frame of reference (closed models)

For context, the May 2026 SWE-bench Verified leaderboard top:

| Model | SWE-V | Notes |
|---|---|---|
| Claude Mythos Preview | 93.9 | closed (Anthropic) |
| Claude Opus 4.7 (Adaptive) | 87.6 | closed (Anthropic) |
| GPT-5.3 Codex | 85.0 | closed (OpenAI) |
| GPT 5.1 Codex Max | 77.9 | closed (OpenAI) |
| Claude Sonnet 4.5 | 77.2 | closed (Anthropic) |

The frontier open models on NIM (deepseek-v4-pro 80.6, minimax-m2.5 80.2) are within ~7 points of the best closed models — and free.

## Sources

Primary (vendor-published, model card / official blog):

- [DeepSeek-V4-Pro · Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro) — SWE-V 80.6, LCB 93.5
- [MiniMax-M2.7 · Hugging Face](https://huggingface.co/MiniMaxAI/MiniMax-M2.7) and [MiniMax launch blog](https://www.minimax.io/news/minimax-m27-en) — SWE-Pro 56.22 (note: vendor card does not include SWE-V)
- [MiniMax M2.5 launch blog](https://www.minimax.io/news/minimax-m25) — SWE-V 80.2
- [Devstral 2 launch (Mistral)](https://mistral.ai/news/devstral-2-vibe-cli) and [model card](https://huggingface.co/mistralai/Devstral-2-123B-Instruct-2512) — SWE-V 72.2
- [Kimi K2.6 tech blog](https://www.kimi.com/blog/kimi-k2-6) — SWE-V 80.2
- [Qwen3-Coder blog](https://qwenlm.github.io/blog/qwen3-coder/) — SOTA on SWE-V among open models

Aggregators (third-party leaderboards):

- [SWE-bench Verified Leaderboard (llm-stats)](https://llm-stats.com/benchmarks/swe-bench-verified)
- [SWE-bench official site](https://www.swebench.com/) and [Verified page](https://www.swebench.com/verified.html)
- [LiveCodeBench Leaderboard](https://livecodebench.github.io/leaderboard.html)
- [SWE-rebench Leaderboard](https://swe-rebench.com/)
- [Scale SWE-Bench Pro Leaderboard](https://labs.scale.com/leaderboard/swe_bench_pro_public)
- [Onyx Open-Source LLM Leaderboard](https://onyx.app/open-llm-leaderboard)

When a vendor and an aggregator disagree, the vendor's number is used (and labelled `swebench`). Aggregator-only numbers get the `livecodebench` / `humaneval` / `estimate` label depending on which benchmark it is.

## Contributing benchmark updates

If a new model lands or a vendor updates their model card with a real SWE-V score, the change is small:

1. Edit `claude-free-audit.py`.
2. In the `BENCHMARKS` dict, add or update the entry. Keep keys sorted by `code_score` descending within their tier comment block:

```python
"vendor/model-id": {"swebench": 78.5, "code_score": 78.5, "src": "swebench"},
```

3. If the model belongs to the curated default (frontier or strong tier), add it to `CURATED` in the right position. Add a `# 78.5` trailing comment so re-orderings stay readable.
4. (Optional) Update `docs/BENCHMARKS.md` (this file) to reflect the new entry.
5. PR.

Ground rules:

- Never fabricate a SWE-bench score. If only LiveCodeBench is available, use `"livecodebench": X, "code_score": X, "src": "livecodebench"`. If nothing concrete is published, use `"estimate"` as the source — the audit display warns users.
- Don't average across benchmarks. Pick the most relevant one for code (SWE-V > LCB > HumanEval) and use that as `code_score`.
- Do include the secondary scores (`livecodebench`, `humaneval`) in the dict for transparency, even if they don't drive `code_score`.
- Cite the source in the PR description.

## When the table is wrong

If `claude-free calibrate` picks a model you know is bad — or skips one that should win — the table's `code_score` for those models is probably wrong. Open an issue with:

- Which model
- The score you'd put on it
- The source (vendor card / leaderboard URL)

A bad code score can cascade — the calibrate walk goes top-down, so if a 30-pt model is mistakenly tagged 80, calibrate may pick it. Fixes here have outsized value.
