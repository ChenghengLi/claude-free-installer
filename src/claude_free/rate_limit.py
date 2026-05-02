"""Sliding-window rate limiter. Keeps us under NIM's ~40 req/min ceiling."""

from __future__ import annotations

import collections
import time


class RateLimiter:
    """Sliding-window rate limiter.

    Free NVIDIA NIM is ~40 req/min/key; we default callers to 30/min to
    leave headroom for the proxy and other concurrent use. Call .wait()
    before every outbound request — it sleeps as needed and returns the
    number of seconds slept (for telemetry).
    """

    def __init__(self, rate_per_min: float):
        self.rate = max(1.0, float(rate_per_min))
        self.window = 60.0
        self.timestamps: collections.deque[float] = collections.deque()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def wait(self) -> float:
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
