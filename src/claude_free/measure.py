"""Measurement loop — warmup + N runs of provider.probe(), median TTFT."""

from __future__ import annotations

import statistics
from typing import Optional

from claude_free.providers.base import Provider
from claude_free.rate_limit import RateLimiter


def _median(values: list[int]) -> int:
    return int(statistics.median(values))


def measure(
    provider: Provider,
    model: str,
    runs: int,
    timeout: float,
    do_warmup: bool,
    rate_limiter: Optional[RateLimiter] = None,
    warmup_timeout: Optional[float] = None,
) -> dict:
    """Warmup + `runs` measured probes. Returns aggregated stats or {error: str}."""
    if do_warmup:
        # Cold-start can be much slower than steady-state on NIM (some models
        # take 60-90s on first call). Give the warmup a bigger budget than
        # measured runs so we don't blackball slow-cold/fast-warm models.
        wt = warmup_timeout if warmup_timeout is not None else max(timeout * 2.5, 90.0)
        provider.probe(model, wt, rate_limiter=rate_limiter)  # discard
    samples: list[dict] = []
    for _ in range(runs):
        samples.append(provider.probe(model, timeout, rate_limiter=rate_limiter))
    ok = [s for s in samples if not s.get("error") and s.get("ttft_ms") is not None]
    if not ok:
        first_err = next((s for s in samples if s.get("error")), {"error": "no successful runs"})
        return {"model": model, "error": first_err.get("error")}
    ttfts = [s["ttft_ms"] for s in ok]
    totals = [s["total_ms"] for s in ok]
    tpss = [s["tok_per_s"] for s in ok if s.get("tok_per_s")]
    return {
        "model": model,
        "ttft_ms": _median(ttfts),
        "ttft_min_ms": min(ttfts),
        "ttft_max_ms": max(ttfts),
        "total_ms": _median(totals),
        "tok_per_s": round(statistics.mean(tpss), 1) if tpss else None,
        "samples": len(ok),
        "sample_text": ok[-1].get("sample", ""),
    }
