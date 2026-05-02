"""OpenRouter provider — talks to https://openrouter.ai/api/v1.

OpenAI-compatible chat-completions endpoint with SSE streaming. OpenRouter
aggregates many providers behind a single API: free-tier models (suffixed
:free), Anthropic, OpenAI, Mistral, Meta, etc. Auth is a Bearer key
(sk-or-v1-...).

Set the key with $OPENROUTER_API_KEY (the script falls back to .env if
configured).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from claude_free.rate_limit import RateLimiter

PROMPT = "Reply with exactly the single word: pong."
MAX_TOKENS = 16


class OpenRouterProvider:
    """OpenAI-compatible client for OpenRouter."""

    name = "openrouter"
    api_base = "https://openrouter.ai/api/v1"
    proxy_value_prefix = "openrouter/"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenRouter API key is required (sk-or-v1-...)")
        self.api_key = api_key
        # OpenRouter recommends setting these to attribute usage. They're
        # optional; we keep the values minimal and override-able from env.
        self.referer = os.environ.get(
            "OPENROUTER_HTTP_REFERER",
            "https://github.com/ChenghengLi/claude-free-installer",
        )
        self.app_title = os.environ.get("OPENROUTER_X_TITLE", "claude-free-audit")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "HTTP-Referer": self.referer,
            "X-Title": self.app_title,
        }

    def list_models(self, timeout: float = 15.0) -> list[str]:
        req = urllib.request.Request(
            f"{self.api_base}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return sorted(set(ids))

    def probe(
        self,
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
        headers = self._headers()
        # OpenRouter's chat endpoint is /chat/completions, same shape as OpenAI.
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data,
            method="POST",
            headers=headers,
        )
        if rate_limiter is not None:
            rate_limiter.wait()
        t0 = time.perf_counter()
        ttft: Optional[float] = None
        tokens = 0
        text_parts: list[str] = []
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                for raw in r:
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    # OpenRouter sometimes emits SSE comments (lines starting
                    # with ":") to keep the connection alive — ignore those.
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
                return self.probe(model, timeout, rate_limiter, retry_on_429=False)
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
