"""NVIDIA NIM provider — talks to https://integrate.api.nvidia.com/v1.

OpenAI-compatible chat-completions endpoint with SSE streaming. Free tier
caps each key at ~40 req/min.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

from claude_free.rate_limit import RateLimiter

PROMPT = "Reply with exactly the single word: pong."
MAX_TOKENS = 16


class NvidiaNimProvider:
    """OpenAI-compatible client for NVIDIA NIM."""

    name = "nvidia-nim"
    api_base = "https://integrate.api.nvidia.com/v1"
    proxy_value_prefix = "nvidia_nim/"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("NVIDIA API key is required")
        self.api_key = api_key

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
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
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
