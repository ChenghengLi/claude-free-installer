"""Abstract Provider interface.

A provider knows how to talk to one inference API (OpenAI-compatible or not).
The audit and calibrate commands use Provider methods so they don't have to
care which backend they're hitting.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol

from claude_free.rate_limit import RateLimiter


# Heuristics for non-chat endpoints we should never probe with /chat/completions.
NON_CHAT_PATTERNS = re.compile(
    r"(embed|rerank|guard|nemoguard|safety|nv-embed|colpali|"
    r"asr|speech|tts|riva|stable-diffusion|sdxl|flux|"
    r"vision-only|nv-clip|clip-)",
    re.I,
)


class Provider(Protocol):
    """One inference backend. Implementations live in this package."""

    name: str
    """Short CLI-friendly identifier, e.g. 'nvidia-nim'."""

    api_base: str
    """Base URL, e.g. 'https://integrate.api.nvidia.com/v1'."""

    proxy_value_prefix: str
    """The string that goes before the model id when writing to .env.
    E.g. 'nvidia_nim/' -> a model 'meta/llama-3' becomes 'nvidia_nim/meta/llama-3'.
    Empty string for providers that use the model id verbatim."""

    def __init__(self, api_key: str): ...

    def list_models(self, timeout: float = 15.0) -> list[str]:
        """Return all model ids available to this key."""
        ...

    def probe(
        self,
        model: str,
        timeout: float,
        rate_limiter: Optional[RateLimiter] = None,
        retry_on_429: bool = True,
    ) -> dict:
        """Send one short streaming chat request, return TTFT + tokens.

        Returns a dict with one of:
        - on success: {model, ttft_ms, total_ms, tokens, tok_per_s, sample}
        - on failure: {model, error: str}
        """
        ...
