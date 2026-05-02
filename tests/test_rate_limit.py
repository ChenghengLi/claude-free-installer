"""Tests for the sliding-window rate limiter."""

from __future__ import annotations

import time

from claude_free.rate_limit import RateLimiter


def test_first_calls_dont_block():
    limiter = RateLimiter(rate_per_min=60)  # 1 per second average
    t0 = time.monotonic()
    for _ in range(5):
        slept = limiter.wait()
        assert slept == 0
    assert time.monotonic() - t0 < 0.1  # essentially instant


def test_burst_at_limit_blocks():
    """If we've used the budget, the next call sleeps until the window slides."""
    # 4/min = 1 every 15 seconds. We'll set window to 60s and rate to 4 to
    # avoid waiting 15s in the test — instead we forge timestamps directly.
    limiter = RateLimiter(rate_per_min=4)
    limiter.window = 0.5  # shrink the window for the test
    # Fill the bucket
    for _ in range(4):
        limiter.wait()
    t0 = time.monotonic()
    limiter.wait()  # should sleep ~0.5s for the oldest entry to roll off
    elapsed = time.monotonic() - t0
    assert 0.4 < elapsed < 0.7, f"expected ~0.5s sleep, got {elapsed:.2f}s"


def test_zero_rate_is_clamped_to_one():
    """rate=0 would divide-by-zero or never let any call through; the
    constructor clamps to a floor of 1 to keep the limiter usable."""
    limiter = RateLimiter(rate_per_min=0)
    assert limiter.rate >= 1.0


def test_eviction_after_window():
    limiter = RateLimiter(rate_per_min=2)
    limiter.window = 0.2
    limiter.wait()
    limiter.wait()
    time.sleep(0.25)  # let entries expire
    t0 = time.monotonic()
    limiter.wait()  # should not block
    assert time.monotonic() - t0 < 0.05
