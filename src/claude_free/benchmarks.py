"""Static code-benchmark scores for NVIDIA NIM models + scoring helpers.

The BENCHMARKS dict is the single source of truth for "how good at code is
this model". Source priority for each entry: SWE-bench Verified > LiveCodeBench
> HumanEval > estimate. The `src` field flags which one was used so the audit
display can tell users when they're looking at a guess vs a verified number.

Snapshot: 2026-05-02. See docs/BENCHMARKS.md for sources and methodology.
"""

from __future__ import annotations

import math
from typing import Optional

# Curated shortlist of code/chat-capable models worth ranking by default.
# Anything not present in the user's account is silently skipped.
# Order = SWE-bench Verified ranking on NVIDIA NIM (May 2026 snapshot).
CURATED = [
    # Frontier (>= 76 SWE-bench Verified)
    "deepseek-ai/deepseek-v4-pro",                  # 80.6
    "minimaxai/minimax-m2.5",                       # 80.2
    "moonshotai/kimi-k2.6",                         # 80.2
    "deepseek-ai/deepseek-v4-flash",                # 79.0
    "minimaxai/minimax-m2.7",                       # 78.0
    "z-ai/glm-5.1",                                 # 78.0 (estimate)
    "z-ai/glm5",                                    # 77.8
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",     # 76.5 (estimate)
    "qwen/qwen3.5-397b-a17b",                       # 76.4
    "nvidia/llama-3.3-nemotron-super-49b-v1",       # 76.4
    # Strong (60-75)
    "moonshotai/kimi-k2-instruct-0905",             # 73.0 (estimate)
    "mistralai/devstral-2-123b-instruct-2512",      # 72.2
    "moonshotai/kimi-k2-thinking",                  # 71.0 (estimate)
    "qwen/qwen3-coder-480b-a35b-instruct",          # 70.0
    "qwen/qwen3.5-122b-a10b",                       # 70.0 (estimate)
    "z-ai/glm4.7",                                  # 70.0 (estimate)
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",      # 68.0 (estimate)
    "deepseek-ai/deepseek-v3.2",                    # 67.8
    "deepseek-ai/deepseek-v3.1-terminus",           # 62.0 (estimate)
    "nvidia/nemotron-3-super-120b-a12b",            # 60.5
    # Mid (35-60)
    "mistralai/mistral-large-3-675b-instruct-2512", # 58.0 (estimate)
    "meta/llama-4-maverick-17b-128e-instruct",      # 55.0 (estimate)
    "qwen/qwen2.5-72b-instruct",                    # 50.0 (LCB)
    "qwen/qwen3-next-80b-a3b-thinking",             # 50.0 (estimate)
    "qwen/qwen2.5-coder-32b-instruct",              # 50.0
    "deepseek-ai/deepseek-r1",                      # 49.2
    "mistralai/mistral-medium-3.5-128b",            # 45.0 (estimate)
    # Lower / fast tier (kept for comparison)
    "openai/gpt-oss-120b",                          # 30.0
    "meta/llama-3.3-70b-instruct",                  # 30.0 (estimate)
    "openai/gpt-oss-20b",                           # 15.0 (estimate)
    "mistralai/mixtral-8x22b-instruct-v0.1",        # 22.0
    "meta/llama-3.1-8b-instruct",                   # 12.0
]

# Last refreshed: 2026-05-02. Vendor model cards / official leaderboards.
BENCHMARKS: dict[str, dict] = {
    # ---- frontier (>= 76) ----
    "deepseek-ai/deepseek-v4-pro":                 {"swebench": 80.6, "code_score": 80.6, "src": "swebench"},
    "minimaxai/minimax-m2.5":                      {"swebench": 80.2, "code_score": 80.2, "src": "swebench"},
    "moonshotai/kimi-k2.6":                        {"swebench": 80.2, "code_score": 80.2, "src": "swebench"},
    "deepseek-ai/deepseek-v4-flash":               {"swebench": 79.0, "code_score": 79.0, "src": "swebench"},
    "minimaxai/minimax-m2.7":                      {"swebench": 78.0, "code_score": 78.0, "src": "swebench"},
    "z-ai/glm-5.1":                                {"swebench": 78.0, "code_score": 78.0, "src": "estimate"},
    "z-ai/glm5":                                   {"swebench": 77.8, "code_score": 77.8, "src": "swebench"},
    "nvidia/llama-3.3-nemotron-super-49b-v1.5":    {"swebench": 76.5, "code_score": 76.5, "src": "estimate"},
    "qwen/qwen3.5-397b-a17b":                      {"swebench": 76.4, "code_score": 76.4, "src": "swebench"},
    "nvidia/llama-3.3-nemotron-super-49b-v1":      {"swebench": 76.4, "livecodebench": 83.6, "code_score": 76.4, "src": "swebench"},
    # ---- strong (60-75) ----
    "moonshotai/kimi-k2-instruct-0905":            {"swebench": 73.0, "code_score": 73.0, "src": "estimate"},
    "mistralai/devstral-2-123b-instruct-2512":     {"swebench": 72.2, "code_score": 72.2, "src": "swebench"},
    "moonshotai/kimi-k2-thinking":                 {"swebench": 71.0, "code_score": 71.0, "src": "estimate"},
    "qwen/qwen3-coder-480b-a35b-instruct":         {"swebench": 70.0, "code_score": 70.0, "src": "swebench"},
    "moonshotai/kimi-k2-instruct":                 {"swebench": 70.0, "code_score": 70.0, "src": "estimate"},
    "qwen/qwen3.5-122b-a10b":                      {"swebench": 70.0, "code_score": 70.0, "src": "estimate"},
    "z-ai/glm4.7":                                 {"livecodebench": 84.9, "humaneval": 94.2, "code_score": 70.0, "src": "estimate"},
    "nvidia/llama-3.1-nemotron-ultra-253b-v1":     {"swebench": 68.0, "code_score": 68.0, "src": "estimate"},
    "deepseek-ai/deepseek-v3.2":                   {"swebench": 67.8, "code_score": 67.8, "src": "swebench"},
    "deepseek-ai/deepseek-v3":                     {"swebench": 67.8, "code_score": 67.8, "src": "swebench"},
    "deepseek-ai/deepseek-v3.1-terminus":          {"swebench": 62.0, "code_score": 62.0, "src": "estimate"},
    "nvidia/nemotron-3-super-120b-a12b":           {"swebench": 60.5, "code_score": 60.5, "src": "swebench"},
    # ---- mid (35-60) ----
    "mistralai/mistral-large-3-675b-instruct-2512":{"swebench": 58.0, "code_score": 58.0, "src": "estimate"},
    "meta/llama-4-maverick-17b-128e-instruct":     {"swebench": 55.0, "code_score": 55.0, "src": "estimate"},
    "qwen/qwen2.5-72b-instruct":                   {"livecodebench": 55.5, "humaneval": 86.6, "code_score": 50.0, "src": "livecodebench"},
    "qwen/qwen3-next-80b-a3b-thinking":            {"swebench": 50.0, "code_score": 50.0, "src": "estimate"},
    "qwen/qwen2.5-coder-32b-instruct":             {"livecodebench": 38.0, "humaneval": 92.7, "code_score": 50.0, "src": "estimate"},
    "deepseek-ai/deepseek-r1":                     {"swebench": 49.2, "livecodebench": 65.9, "code_score": 49.2, "src": "swebench"},
    "mistralai/mistral-medium-3.5-128b":           {"swebench": 45.0, "code_score": 45.0, "src": "estimate"},
    "meta/llama-3.1-405b-instruct":                {"livecodebench": 85.0, "humaneval": 89.0, "code_score": 45.0, "src": "estimate"},
    "mistralai/mistral-medium-3-instruct":         {"swebench": 40.0, "code_score": 40.0, "src": "estimate"},
    # ---- lower / fast tier (<= 35) ----
    "meta/llama-3.3-70b-instruct":                 {"livecodebench": 33.3, "humaneval": 88.4, "code_score": 30.0, "src": "estimate"},
    "mistralai/mistral-large-2-instruct":          {"swebench": 30.0, "humaneval": 92.0, "code_score": 32.0, "src": "estimate"},
    "qwen/qwen3-next-80b-a3b-instruct":            {"swebench": 30.0, "code_score": 30.0, "src": "swebench"},
    "openai/gpt-oss-120b":                         {"swebench": 30.0, "livecodebench": 60.0, "code_score": 30.0, "src": "swebench"},
    "nvidia/llama-3.1-nemotron-70b-instruct":      {"humaneval": 80.0, "code_score": 30.0, "src": "estimate"},
    "01-ai/yi-large":                              {"humaneval": 81.8, "code_score": 28.0, "src": "estimate"},
    "meta/llama-3.1-70b-instruct":                 {"livecodebench": 28.5, "humaneval": 80.5, "code_score": 25.0, "src": "estimate"},
    "google/gemma-3-27b-it":                       {"humaneval": 80.0, "code_score": 25.0, "src": "estimate"},
    "mistralai/mixtral-8x22b-instruct-v0.1":       {"livecodebench": 25.0, "humaneval": 75.0, "code_score": 22.0, "src": "estimate"},
    "google/gemma-2-27b-it":                       {"humaneval": 71.0, "code_score": 18.0, "src": "estimate"},
    "openai/gpt-oss-20b":                          {"swebench": 15.0, "code_score": 15.0, "src": "estimate"},
    "meta/llama-3.1-8b-instruct":                  {"humaneval": 72.6, "code_score": 12.0, "src": "estimate"},
}


def code_score_for(model: str) -> Optional[dict]:
    """Return {'score': float, 'src': str, ...} for a model, or None if unknown."""
    b = BENCHMARKS.get(model)
    if not b:
        return None
    return {
        "score": b.get("code_score"),
        "src": b.get("src", "?"),
        "swebench": b.get("swebench"),
        "livecodebench": b.get("livecodebench"),
        "humaneval": b.get("humaneval"),
    }


def combined_score(code: Optional[float], ttft_ms: Optional[int], tau_ms: float) -> Optional[float]:
    """Combine quality + speed using TTFT only. Higher = better.

    combined = code_score * exp(-TTFT_ms / tau_ms)

    At TTFT=tau, you keep ~37% of the model's quality score. tau=3000ms means
    a 3s TTFT discounts a model heavily, while sub-300ms keeps ~90% of credit.

    This formula ignores tok/s (post-TTFT generation speed). For a metric
    that accounts for both, use smart_score().
    """
    if code is None or ttft_ms is None:
        return None
    return code * math.exp(-ttft_ms / tau_ms)


# Floor for measured tok/s in smart_score. Our probes use max_tokens=16, which
# makes tok/s readings noisy — a real production model averaging 80 tok/s might
# look like 2 tok/s on the probe because the first few chunks dominate.
# Treating anything below this floor as "the floor" prevents probe noise from
# tanking otherwise-good models. Real models on free NIM stream at 10+ tok/s
# steady-state once warmed up.
_TOK_PER_S_FLOOR = 10.0


def smart_score(
    code: Optional[float],
    ttft_ms: Optional[int],
    tok_per_s: Optional[float],
    tau_ms: float,
    output_tokens: int = 200,
) -> Optional[float]:
    """Combine quality + end-to-end response time. Higher = better.

    smart = code_score * exp(-effective_ms / tau_ms)
    where effective_ms = TTFT_ms + (output_tokens / max(tok_per_s, FLOOR)) * 1000

    Models the user's wait for a typical Claude Code response (default 200
    output tokens — medium response length). A model with great TTFT but
    abnormally slow throughput gets penalized just like one with poor TTFT
    — both leave the user staring at the screen.

    The tok/s floor (10/s) prevents noisy probe measurements from trashing
    a model. With max_tokens=16 probes we routinely see 1-3 tok/s for models
    that stream at 50-200 tok/s in production; the floor stops that from
    dominating the ranking.

    If tok_per_s is missing entirely, falls back to combined_score (TTFT-only).
    """
    if code is None or ttft_ms is None:
        return None
    if tok_per_s is None or tok_per_s <= 0:
        return combined_score(code, ttft_ms, tau_ms)
    effective_tps = max(tok_per_s, _TOK_PER_S_FLOOR)
    effective_ms = ttft_ms + (output_tokens / effective_tps) * 1000.0
    # effective_ms is typically 10-30x larger than ttft_ms (most of the time
    # is spent generating tokens, not waiting for the first one). Scale tau
    # by 10 internally so the same --tau value produces sensible numbers for
    # both combined (TTFT-only) and smart (TTFT + output time). With tau=3000,
    # smart's effective tau is 30000ms — a 30s end-to-end response keeps 37%.
    smart_tau = tau_ms * 10
    return code * math.exp(-effective_ms / smart_tau)
