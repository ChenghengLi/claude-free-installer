"""Provider plugins. Each provider implements `Provider` from .base and
exposes `list_models()` + `probe()`.

Today we have just NVIDIA NIM, but the seam is here for future providers
(OpenRouter, Together AI, OpenAI, ...). Add a new module under this package,
register it in `register_providers()`, and the audit/calibrate commands can
target it via `--provider name`.
"""

from __future__ import annotations

from claude_free.providers.base import Provider
from claude_free.providers.nvidia_nim import NvidiaNimProvider
from claude_free.providers.openrouter import OpenRouterProvider

# Registry of available providers. Keys are CLI-friendly short names.
_PROVIDERS: dict[str, type[Provider]] = {
    "nvidia-nim": NvidiaNimProvider,
    "openrouter": OpenRouterProvider,
}


def register_providers() -> dict[str, type[Provider]]:
    """Return the provider registry. Mutate to add more."""
    return _PROVIDERS


def get_provider(name: str) -> type[Provider]:
    if name not in _PROVIDERS:
        raise KeyError(f"Unknown provider: {name!r}. Known: {list(_PROVIDERS)}")
    return _PROVIDERS[name]
