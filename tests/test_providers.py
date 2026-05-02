"""Tests for the provider plugin layer.

We don't hit live APIs here — we mock urllib.request.urlopen and verify
each provider sends the expected request shape and parses the expected
response. This is enough to catch regressions in the request/response
contract without flaky network calls.
"""

from __future__ import annotations

import io
import json
import urllib.request
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from claude_free.providers import get_provider, register_providers
from claude_free.providers.nvidia_nim import NvidiaNimProvider
from claude_free.providers.openrouter import OpenRouterProvider


# ----------------------------------------------------------------------------
# Plugin registry
# ----------------------------------------------------------------------------

class TestRegistry:
    def test_nvidia_nim_is_registered(self):
        assert "nvidia-nim" in register_providers()
        assert get_provider("nvidia-nim") is NvidiaNimProvider

    def test_openrouter_is_registered(self):
        assert "openrouter" in register_providers()
        assert get_provider("openrouter") is OpenRouterProvider

    def test_unknown_provider_raises(self):
        with pytest.raises(KeyError):
            get_provider("not-a-real-provider")


# ----------------------------------------------------------------------------
# Provider Protocol surface
# ----------------------------------------------------------------------------

PROVIDER_CLASSES = [
    pytest.param(NvidiaNimProvider, id="nvidia-nim"),
    pytest.param(OpenRouterProvider, id="openrouter"),
]


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
class TestProviderProtocol:
    def test_has_required_attributes(self, cls):
        p = cls("dummy-key")
        assert isinstance(p.name, str) and p.name
        assert p.api_base.startswith("https://")
        assert isinstance(p.proxy_value_prefix, str)

    def test_blank_key_raises(self, cls):
        with pytest.raises(ValueError):
            cls("")


# ----------------------------------------------------------------------------
# Mocked HTTP — verify request shape + response parsing
# ----------------------------------------------------------------------------

@contextmanager
def mock_urlopen(responses: dict[str, object]):
    """Patch urllib.request.urlopen with a function that dispatches by URL.

    `responses` maps URL -> bytes (body) or HTTPError instance.
    The captured Request objects are recorded in `captured` for assertions.
    """
    captured: list[urllib.request.Request] = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        url = req.full_url
        body = responses.get(url) or responses.get("__default__")
        if body is None:
            raise AssertionError(f"No mock response for URL: {url}")

        class _Resp:
            def __init__(self, data: bytes):
                self._data = data
                self._stream = io.BytesIO(data)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return self._data

            def __iter__(self):
                # SSE streams come line-by-line.
                for line in self._data.split(b"\n"):
                    if line:
                        yield line + b"\n"

        return _Resp(body)

    with patch.object(urllib.request, "urlopen", fake_urlopen):
        yield captured


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
class TestListModels:
    def test_returns_sorted_unique_ids(self, cls):
        p = cls("dummy")
        body = json.dumps({
            "data": [
                {"id": "vendor/model-c"},
                {"id": "vendor/model-a"},
                {"id": "vendor/model-b"},
                {"id": "vendor/model-a"},  # duplicate
                {"id": ""},                  # empty -> dropped
                {"foo": "no id key"},        # no id -> dropped
            ]
        }).encode()
        with mock_urlopen({f"{p.api_base}/models": body}):
            ids = p.list_models()
        assert ids == ["vendor/model-a", "vendor/model-b", "vendor/model-c"]


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
class TestProbe:
    def test_records_ttft_and_tokens_from_streaming_response(self, cls):
        p = cls("dummy")
        # Fake SSE stream with three content chunks.
        chunks = [
            b'data: {"choices":[{"delta":{"content":"po"}}]}',
            b'data: {"choices":[{"delta":{"content":"ng"}}]}',
            b'data: {"choices":[{"delta":{}}]}',
            b'data: [DONE]',
        ]
        body = b"\n".join(chunks)
        with mock_urlopen({f"{p.api_base}/chat/completions": body}) as captured:
            r = p.probe("vendor/model-x", timeout=5.0)
        assert r.get("error") is None
        assert r["model"] == "vendor/model-x"
        assert r["ttft_ms"] is not None and r["ttft_ms"] >= 0
        assert r["tokens"] == 2  # "po" + "ng"
        assert "pong" in r["sample"]
        # Verify the request shape
        req = captured[-1]
        assert req.full_url == f"{p.api_base}/chat/completions"
        body_sent = json.loads(req.data)
        assert body_sent["stream"] is True
        assert body_sent["max_tokens"] > 0

    def test_provider_specific_auth_header(self, cls):
        p = cls("super-secret-key")
        body = b'data: {"choices":[{"delta":{"content":"x"}}]}\ndata: [DONE]'
        with mock_urlopen({f"{p.api_base}/chat/completions": body}) as captured:
            p.probe("vendor/model-x", timeout=5.0)
        # Both providers use Bearer token auth
        auth = captured[-1].get_header("Authorization")
        assert auth == "Bearer super-secret-key"


class TestProxyValuePrefix:
    def test_nvidia_prefix(self):
        assert NvidiaNimProvider("dummy").proxy_value_prefix == "nvidia_nim/"

    def test_openrouter_prefix(self):
        assert OpenRouterProvider("dummy").proxy_value_prefix == "openrouter/"
