#!/usr/bin/env python3
"""
claude-free-audit — probe NVIDIA NIM chat models and rank them by latency.

Reads NVIDIA_NIM_API_KEY from ~/free-claude-code/.env (or $NVIDIA_NIM_API_KEY,
or $NVIDIA_API_KEY, in that order).

For each candidate model: sends a tiny streaming chat completion, measures
time-to-first-token (TTFT) and tokens-per-second. Does N=3 measured runs after
1 warmup. Reports the median TTFT.

Optionally rewrites MODEL_OPUS / MODEL_SONNET / MODEL_HAIKU / MODEL in
~/free-claude-code/.env to the lowest-TTFT model.

Stdlib only — no extra deps beyond Python 3.8+.

Usage:
  claude-free audit                 # probe curated shortlist, prompt to set
  claude-free audit --all           # probe every chat-capable model
  claude-free audit --filter llama  # probe ids containing "llama"
  claude-free audit --set           # auto-set winner without prompting
  claude-free audit --no-set        # never offer to set
  claude-free audit --runs 5        # measured runs per model (default 3)
  claude-free audit --timeout 20    # per-probe timeout seconds (default 30)
  claude-free audit --max 8         # max models to probe (default 12)
  claude-free audit --include x/y   # add model id to the candidate list (repeatable)
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


class RateLimiter:
    """Sliding-window rate limiter. Free NVIDIA NIM is ~40 req/min/key; we
    default to 30/min to leave headroom for the proxy and other concurrent
    use. Call .wait() before every outbound request; it sleeps as needed."""

    def __init__(self, rate_per_min: float):
        self.rate = max(1.0, float(rate_per_min))
        self.window = 60.0
        self.timestamps: collections.deque[float] = collections.deque()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def wait(self) -> float:
        """Block until a slot is free. Returns seconds slept (for telemetry)."""
        now = time.monotonic()
        self._evict(now)
        slept = 0.0
        while len(self.timestamps) >= self.rate:
            wait_for = (self.timestamps[0] + self.window) - now + 0.05
            if wait_for > 0:
                time.sleep(wait_for)
                slept += wait_for
            now = time.monotonic()
            self._evict(now)
        self.timestamps.append(now)
        return slept

API_BASE = "https://integrate.api.nvidia.com/v1"

# Curated shortlist of code/chat-capable models worth ranking by default.
# Anything not present in the user's account is silently skipped.
# Order = current SWE-bench Verified ranking on NVIDIA NIM (May 2026 snapshot).
# Keep this in sync with BENCHMARKS below so combined scoring stays meaningful.
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

# Public coding-benchmark scores. Sources: swebench.com, llm-stats.com,
# livecodebench.github.io, swe-rebench.com, vendor tech reports / model cards.
# Last refreshed: 2026-05-02. These scores drift — re-run `claude-free update`
# to pull the freshest table from GitHub. `code_score` is a single 0-100 number
# used for ranking. SWE-bench Verified preferred, then LiveCodeBench, then
# HumanEval, then estimate. Update freely; the ranking math doesn't change.
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
    """Return {'score': float, 'src': str, 'swebench': ..., 'livecodebench': ..., 'humaneval': ...}
    for the given model id, or None if no benchmark data is known."""
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
    """Combine quality and speed into a single score. Higher = better.
    Formula: code_score * exp(-ttft_ms / tau_ms). tau_ms is the latency
    half-life-ish constant — at tau ms of TTFT, the model keeps ~37% of its
    quality score. Default tau=3000ms means a 3-second TTFT discounts a
    model heavily, while 300ms keeps ~90% of its score."""
    if code is None or ttft_ms is None:
        return None
    return code * math.exp(-ttft_ms / tau_ms)

# Heuristics for non-chat endpoints we should never probe with /chat/completions.
NON_CHAT_PATTERNS = re.compile(
    r"(embed|rerank|guard|nemoguard|safety|nv-embed|colpali|"
    r"asr|speech|tts|riva|stable-diffusion|sdxl|flux|"
    r"vision-only|nv-clip|clip-)",
    re.I,
)

PROMPT = "Reply with exactly the single word: pong."
MAX_TOKENS = 16

# ANSI colors — disabled if stdout isn't a TTY or NO_COLOR is set.
def _colors():
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return {k: "" for k in ("B", "D", "G", "Y", "R", "N")}
    return {
        "B": "\033[1m",
        "D": "\033[2m",
        "G": "\033[0;32m",
        "Y": "\033[0;33m",
        "R": "\033[0;31m",
        "N": "\033[0m",
    }


C = _colors()


def env_path() -> Path:
    return Path.home() / "free-claude-code" / ".env"


def read_env_key(path: Path, key: str) -> Optional[str]:
    if not path.exists():
        return None
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        v = m.group(1)
        v = v.split("#", 1)[0].strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        return v
    return None


def write_env_key(path: Path, key: str, value: str) -> None:
    line = f'{key}="{value}"'
    if not path.exists():
        path.write_text(line + "\n", encoding="utf-8")
        return
    txt = path.read_text(encoding="utf-8")
    pat = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")
    if pat.search(txt):
        txt = pat.sub(line, txt)
    else:
        if not txt.endswith("\n"):
            txt += "\n"
        txt += line + "\n"
    path.write_text(txt, encoding="utf-8")


def resolve_api_key() -> Optional[str]:
    for var in ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    return read_env_key(env_path(), "NVIDIA_NIM_API_KEY")


def list_models(api_key: str, timeout: float = 15.0) -> list[str]:
    req = urllib.request.Request(
        f"{API_BASE}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
    return sorted(set(ids))


def probe(
    api_key: str,
    model: str,
    timeout: float,
    rate_limiter: Optional[RateLimiter] = None,
    retry_on_429: bool = True,
) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "stream": True,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    if rate_limiter is not None:
        rate_limiter.wait()
    t0 = time.perf_counter()
    ttft = None
    tokens = 0
    text_parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    continue
                try:
                    j = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = j.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                chunk = delta.get("content")
                if chunk:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    tokens += 1
                    text_parts.append(chunk)
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry_on_429:
            ra = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = float(ra) if ra else 5.0
            except (TypeError, ValueError):
                wait = 5.0
            wait = min(max(wait, 1.0), 30.0)
            time.sleep(wait)
            return probe(api_key, model, timeout, rate_limiter, retry_on_429=False)
        body_txt = ""
        try:
            body_txt = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return {"model": model, "error": f"HTTP {e.code} {body_txt}"}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return {"model": model, "error": f"timeout >{timeout:.1f}s"}
        return {"model": model, "error": f"URL {reason}"}
    except TimeoutError:
        return {"model": model, "error": f"timeout >{timeout:.1f}s"}
    except Exception as e:  # noqa: BLE001
        return {"model": model, "error": f"{type(e).__name__}: {e}"}
    total = time.perf_counter() - t0
    return {
        "model": model,
        "ttft_ms": int(ttft * 1000) if ttft is not None else None,
        "total_ms": int(total * 1000),
        "tokens": tokens,
        "tok_per_s": round(tokens / total, 1) if tokens and total > 0 else None,
        "sample": "".join(text_parts)[:60],
    }


def median(values: list[int]) -> int:
    return int(statistics.median(values))


def fmt_row(model: str, ttft: str, runs: str, tps: str, sample: str, width: int) -> str:
    return f"  {model:<{width}}  {ttft:>10}  {runs:>9}  {tps:>7}  {sample}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="claude-free audit",
        description="Probe NVIDIA NIM chat models for latency and pick the fastest.",
    )
    p.add_argument("--all", action="store_true", help="probe every chat-capable model in your account")
    p.add_argument("--filter", default="", help="only probe model ids containing this substring")
    p.add_argument("--include", action="append", default=[], help="add a specific model id (repeatable)")
    p.add_argument("--runs", type=int, default=3, help="measured runs per model after 1 warmup (default 3)")
    p.add_argument("--timeout", type=float, default=45.0, help="per-probe timeout in seconds (default 45)")
    p.add_argument("--max", type=int, default=15, help="max number of models to probe (default 15)")
    p.add_argument("--no-warmup", action="store_true", help="skip the warmup probe")
    p.add_argument(
        "--by",
        choices=("combined", "ttft", "code"),
        default="combined",
        help="rank winner by: combined (default, fast+good), ttft (fastest), or code (best benchmarks)",
    )
    p.add_argument(
        "--tau",
        type=float,
        default=3000.0,
        help="latency penalty constant in ms (default 3000). lower = penalize slow models harder",
    )
    p.add_argument(
        "--early-exit",
        action="store_true",
        help="walk every benchmarked model in your account in code-score-desc order; "
             "stop and pick the first one whose median TTFT is <= --threshold ms. "
             "this is what `claude-free calibrate` uses.",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="TTFT threshold in ms for --early-exit (default 1000 when --early-exit, else off)",
    )
    p.add_argument(
        "--rate",
        type=float,
        default=30.0,
        help="max requests/min to NVIDIA (default 30; free NIM ceiling is ~40). 0 = no limit",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--set", dest="auto_set", action="store_true", help="auto-set winner to all tiers (no prompt)")
    g.add_argument("--no-set", dest="no_set", action="store_true", help="never offer to set the winner")
    p.add_argument("--key", help="NVIDIA API key (overrides env / .env)")
    p.add_argument("--env-file", help="path to free-claude-code .env (default ~/free-claude-code/.env)")
    return p.parse_args(argv)


def select_candidates(args: argparse.Namespace, available: list[str]) -> list[str]:
    chat_only = [m for m in available if not NON_CHAT_PATTERNS.search(m)]

    if args.early_exit:
        # Quality-priority walk: every benchmarked model present in the
        # account, sorted by code_score descending. We use BENCHMARKS as
        # the source of truth for quality ranking so calibrate sees every
        # known model regardless of CURATED ordering.
        if args.filter:
            f = args.filter.lower()
            base = [m for m in chat_only if f in m.lower() and m in BENCHMARKS]
        else:
            base = [m for m in BENCHMARKS if m in chat_only]
        cands = sorted(base, key=lambda m: -(BENCHMARKS[m].get("code_score") or 0))
    elif args.all:
        cands = chat_only
    elif args.filter:
        f = args.filter.lower()
        cands = [m for m in chat_only if f in m.lower()]
    else:
        cands = [m for m in CURATED if m in chat_only]

    for extra in args.include:
        if extra in available and extra not in cands:
            cands.append(extra)
    # Stable de-dup, cap at --max
    seen: set[str] = set()
    out: list[str] = []
    for m in cands:
        if m in seen:
            continue
        seen.add(m)
        out.append(m)
        if len(out) >= args.max:
            break
    return out


def measure(
    api_key: str,
    model: str,
    runs: int,
    timeout: float,
    do_warmup: bool,
    rate_limiter: Optional[RateLimiter] = None,
    warmup_timeout: Optional[float] = None,
) -> dict:
    if do_warmup:
        # Cold-start can be much slower than steady-state on NIM (some models
        # take 60-90s on first call). Give the warmup a bigger budget than
        # measured runs so we don't blackball slow-cold/fast-warm models.
        wt = warmup_timeout if warmup_timeout is not None else max(timeout * 2.5, 90.0)
        probe(api_key, model, wt, rate_limiter=rate_limiter)  # discard
    samples: list[dict] = []
    for _ in range(runs):
        samples.append(probe(api_key, model, timeout, rate_limiter=rate_limiter))
    ok = [s for s in samples if not s.get("error") and s.get("ttft_ms") is not None]
    if not ok:
        # Return the first error we saw so we can show why it failed.
        first_err = next((s for s in samples if s.get("error")), {"error": "no successful runs"})
        return {"model": model, "error": first_err.get("error")}
    ttfts = [s["ttft_ms"] for s in ok]
    totals = [s["total_ms"] for s in ok]
    tpss = [s["tok_per_s"] for s in ok if s.get("tok_per_s")]
    return {
        "model": model,
        "ttft_ms": median(ttfts),
        "ttft_min_ms": min(ttfts),
        "ttft_max_ms": max(ttfts),
        "total_ms": median(totals),
        "tok_per_s": round(statistics.mean(tpss), 1) if tpss else None,
        "samples": len(ok),
        "sample_text": ok[-1].get("sample", ""),
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    api_key = args.key or resolve_api_key()
    if not api_key:
        print(
            f"{C['R']}No NVIDIA API key found.{C['N']} Set NVIDIA_NIM_API_KEY or "
            f"populate {env_path()}.",
            file=sys.stderr,
        )
        return 2

    env_file = Path(args.env_file) if args.env_file else env_path()
    limiter = RateLimiter(args.rate) if args.rate and args.rate > 0 else None

    print(f"{C['B']}claude-free audit{C['N']}  {C['D']}-- ranking NVIDIA NIM chat models by TTFT and code benchmarks{C['N']}\n")
    if limiter is not None:
        print(f"  {C['D']}rate limit: {args.rate:.0f} req/min sliding window (sleep before bursts){C['N']}")
    print(f"  fetching model catalogue from {API_BASE}/models ...", end=" ", flush=True)
    try:
        available = list_models(api_key)
    except Exception as e:  # noqa: BLE001
        print(f"{C['R']}failed{C['N']}: {e}")
        return 1
    print(f"{C['G']}{len(available)} models{C['N']}")

    candidates = select_candidates(args, available)
    if not candidates:
        print(f"{C['Y']}No matching models. Try --all or --filter <substr>.{C['N']}")
        return 1

    runs = max(1, args.runs)

    # ----- early-exit (quality-priority) path: used by `claude-free calibrate` -----
    if args.early_exit:
        threshold = args.threshold if args.threshold > 0 else 1000.0
        # Dynamic per-probe timeout: a model that's going to be too slow gets
        # cut off shortly after the threshold. Threshold 1000ms -> 1.5s probe
        # timeout. Saves ~30s per slow model vs the default --timeout.
        measured_timeout = (threshold / 1000.0) + 0.5
        # Warmup gets a moderately bigger budget so a recently-warm model has
        # time to respond, but we don't sit on a fully-cold 1T-param model
        # for 90s — calibrate is about "fastest good model RIGHT NOW", and
        # something that needs 60s of cold-load isn't fast right now.
        warmup_timeout = max(measured_timeout * 5, 10.0)
        # One passing measurement is enough to declare a winner. The default
        # --runs is for audit's full ranking; calibrate doesn't need 3.
        ee_runs = 1
        print(
            f"  walking {len(candidates)} benchmarked model(s) by code-score desc, "
            f"first one with TTFT <= {C['G']}{threshold:.0f} ms{C['N']} wins\n"
            f"  {C['D']}per-probe timeout: warmup {warmup_timeout:.0f}s, measured "
            f"{measured_timeout:.1f}s, {ee_runs} measured run/model{C['N']}\n"
        )
        winner_record: Optional[dict] = None
        all_results: list[dict] = []
        for i, m in enumerate(candidates, 1):
            bench = code_score_for(m) or {}
            cs = bench.get("score")
            cs_str = f"{cs:.1f}" if cs is not None else "n/a"
            print(
                f"  [{i:>2}/{len(candidates)}] {m:<55} "
                f"code={C['G']}{cs_str:>5}{C['N']}  ",
                end="", flush=True,
            )
            r = measure(
                api_key, m, ee_runs, measured_timeout,
                do_warmup=not args.no_warmup,
                rate_limiter=limiter,
                warmup_timeout=warmup_timeout,
            )
            r["code_score"] = cs
            r["code_src"] = bench.get("src")
            all_results.append(r)
            if r.get("error"):
                print(f"{C['R']}{r['error'][:60]}{C['N']}")
                continue
            r["combined"] = combined_score(cs, r.get("ttft_ms"), args.tau)
            ttft = r["ttft_ms"]
            ok_speed = ttft is not None and ttft <= threshold
            tag = f"{C['G']}WINNER{C['N']}" if ok_speed else f"{C['Y']}slow{C['N']}"
            print(
                f"TTFT {C['B']}{ttft:>5} ms{C['N']}  "
                f"({r['samples']} runs)  -> {tag}"
            )
            if ok_speed:
                winner_record = r
                break

        if winner_record is None:
            # Nothing met the threshold. Fall back to the best combined score
            # from what we did measure, so calibrate still sets *something*.
            ok = [
                r for r in all_results
                if not r.get("error")
                and r.get("ttft_ms") is not None
                and r.get("combined") is not None
            ]
            if not ok:
                print(f"\n{C['R']}No model met threshold and no successful probes either.{C['N']}")
                return 1
            ok.sort(key=lambda r: -r["combined"])
            winner_record = ok[0]
            print(
                f"\n{C['Y']}No model met TTFT <= {threshold:.0f} ms. "
                f"Falling back to best combined score: {winner_record['model']} "
                f"(TTFT {winner_record['ttft_ms']} ms, code {winner_record.get('code_score')}).{C['N']}"
            )

        winner = winner_record["model"]
        proxy_value = winner if winner.startswith("nvidia_nim/") else f"nvidia_nim/{winner}"
        print(
            f"\n{C['B']}Picked:{C['N']} {C['G']}{winner}{C['N']}  "
            f"(TTFT {winner_record['ttft_ms']} ms, code {winner_record.get('code_score')}, "
            f"src {winner_record.get('code_src', '?')})"
        )
        print(f"  -> {proxy_value}")

        if args.no_set:
            print(f"{C['D']}--no-set: leaving {env_file} alone.{C['N']}")
            return 0
        if not env_file.exists():
            print(
                f"{C['Y']}Skipping .env update: {env_file} not found "
                f"(install claude-free first).{C['N']}"
            )
            return 0
        if not args.auto_set:
            try:
                ans = input(
                    f"\nSet {C['B']}MODEL_OPUS / MODEL_SONNET / MODEL_HAIKU / MODEL{C['N']} "
                    f"to {C['G']}{proxy_value}{C['N']} in {env_file}? [Y/n] "
                ).strip().lower()
            except EOFError:
                ans = ""
            if ans not in ("", "y", "yes"):
                print("Skipped -- .env unchanged.")
                return 0
        for k in ("MODEL_OPUS", "MODEL_SONNET", "MODEL_HAIKU", "MODEL"):
            write_env_key(env_file, k, proxy_value)
        print(f"{C['G']}Updated {env_file}.{C['N']}")
        print(
            f"{C['D']}Restart any running proxy: `claude-free stop && claude-free` "
            f"to pick up the new tier mapping.{C['N']}"
        )
        return 0

    # ----- full-sweep path: used by `claude-free audit` -----
    print(
        f"  probing {len(candidates)} model(s), "
        f"{'no warmup, ' if args.no_warmup else '1 warmup + '}{runs} measured run(s) each, "
        f"timeout {args.timeout:.0f}s\n"
    )

    width = max(len(m) for m in candidates) + 2
    width = min(width, 55)
    header = (
        f"  {'MODEL':<{width}}  {'TTFT(ms)':>10}  {'TOK/S':>7}  "
        f"{'CODE':>6}  {'COMBINED':>9}  SRC"
    )
    print(f"{C['B']}{header}{C['N']}")
    print("  " + "-" * (width + 50))

    results: list[dict] = []
    for m in candidates:
        # Print model name immediately so a slow probe is visible.
        print(f"  {m:<{width}}  ", end="", flush=True)
        r = measure(
            api_key, m, runs, args.timeout,
            do_warmup=not args.no_warmup,
            rate_limiter=limiter,
        )
        bench = code_score_for(m)
        if bench:
            r["code_score"] = bench["score"]
            r["code_src"] = bench["src"]
            r["bench_detail"] = bench
        if r.get("error"):
            print(f"{C['R']}ERROR{C['N']}  {r['error'][:80]}")
        else:
            r["combined"] = combined_score(r.get("code_score"), r.get("ttft_ms"), args.tau)
            cs = r.get("code_score")
            cb = r.get("combined")
            cs_str = f"{cs:.1f}" if cs is not None else "-"
            cb_str = f"{cb:.1f}" if cb is not None else "-"
            tok = r.get("tok_per_s")
            tok_str = f"{tok}" if tok is not None else "-"
            print(
                f"{r['ttft_ms']:>10}  "
                f"{tok_str:>7}  "
                f"{cs_str:>6}  "
                f"{cb_str:>9}  "
                f"{r.get('code_src', '?')}"
            )
        results.append(r)

    ok = [r for r in results if not r.get("error") and r.get("ttft_ms") is not None]
    if not ok:
        print(f"\n{C['R']}No successful probes -- nothing to rank.{C['N']}")
        return 1

    def _print_ranking(title: str, sorted_list: list[dict], score_fn, score_label: str) -> None:
        print(f"\n{C['B']}{title}:{C['N']}")
        for i, r in enumerate(sorted_list, 1):
            marker = "*" if i == 1 else " "
            score = score_fn(r)
            score_str = f"{score:.1f}" if isinstance(score, float) else str(score)
            print(
                f"  {marker} {i:>2}. {r['model']:<{width}}  "
                f"{C['G']}{score_str:>7}{C['N']}  {score_label}  "
                f"({C['D']}TTFT {r['ttft_ms']} ms, "
                f"code {r.get('code_score') if r.get('code_score') is not None else 'n/a'}{C['N']})"
            )

    by_ttft = sorted(ok, key=lambda r: r["ttft_ms"])
    by_code = sorted(
        [r for r in ok if r.get("code_score") is not None],
        key=lambda r: -r["code_score"],
    )
    by_combined = sorted(
        [r for r in ok if r.get("combined") is not None],
        key=lambda r: -r["combined"],
    )

    _print_ranking("Lowest TTFT", by_ttft, lambda r: r["ttft_ms"], "ms")
    if by_code:
        _print_ranking("Best code-benchmark score", by_code, lambda r: r["code_score"], "pts")
    if by_combined:
        _print_ranking(
            f"Combined fast+good (tau={args.tau:.0f}ms)",
            by_combined,
            lambda r: r["combined"],
            "score",
        )

    # Pick the winner by the requested ranking. Fall back to TTFT if the chosen
    # ranking has no entries (e.g., --by combined but no model has benchmark data).
    if args.by == "combined" and by_combined:
        winner_record = by_combined[0]
        ranking_used = "combined fast+good"
    elif args.by == "code" and by_code:
        winner_record = by_code[0]
        ranking_used = "code benchmark"
    else:
        winner_record = by_ttft[0]
        ranking_used = "lowest TTFT"
        if args.by != "ttft":
            print(
                f"\n{C['Y']}note: --by {args.by} had no eligible models "
                f"(missing benchmark data); falling back to TTFT.{C['N']}"
            )

    winner = winner_record["model"]
    proxy_value = winner if winner.startswith("nvidia_nim/") else f"nvidia_nim/{winner}"
    print(
        f"\n{C['B']}Winner ({ranking_used}):{C['N']} {C['G']}{winner}{C['N']}  "
        f"-> {proxy_value}"
    )

    if args.no_set:
        print(f"{C['D']}--no-set: leaving {env_file} alone.{C['N']}")
        return 0

    if not env_file.exists():
        print(
            f"{C['Y']}Skipping .env update: {env_file} not found "
            f"(install claude-free first).{C['N']}"
        )
        return 0

    if not args.auto_set:
        try:
            ans = input(
                f"\nSet {C['B']}MODEL_OPUS / MODEL_SONNET / MODEL_HAIKU / MODEL{C['N']} "
                f"to {C['G']}{proxy_value}{C['N']} in {env_file}? [Y/n] "
            ).strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("", "y", "yes"):
            print("Skipped — .env unchanged.")
            return 0

    for k in ("MODEL_OPUS", "MODEL_SONNET", "MODEL_HAIKU", "MODEL"):
        write_env_key(env_file, k, proxy_value)
    print(f"{C['G']}Updated {env_file}.{C['N']}")
    print(
        f"{C['D']}Restart any running proxy: `claude-free stop && claude-free` "
        f"to pick up the new tier mapping.{C['N']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
