"""`claude-free audit` — full sweep + three rankings.

Also hosts the early-exit code path used by `claude-free calibrate`,
which is just audit with --set --early-exit --threshold 1000.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from claude_free.benchmarks import (
    BENCHMARKS,
    CURATED,
    code_score_for,
    combined_score,
)
from claude_free.colors import colors
from claude_free.env import env_path, write_env_key
from claude_free.measure import measure
from claude_free.providers.base import NON_CHAT_PATTERNS, Provider
from claude_free.rate_limit import RateLimiter


def select_candidates(args: argparse.Namespace, available: list[str]) -> list[str]:
    """Build the candidate list from CLI flags + the available model set."""
    chat_only = [m for m in available if not NON_CHAT_PATTERNS.search(m)]

    if args.early_exit:
        # Quality-priority walk: every benchmarked model present in the
        # account, sorted by code_score descending. We use BENCHMARKS as
        # the source of truth so calibrate sees every known model regardless
        # of CURATED ordering.
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


def _maybe_write_env(
    args: argparse.Namespace,
    env_file: Path,
    proxy_value: str,
    C: dict[str, str],
) -> None:
    if args.no_set:
        print(f"{C['D']}--no-set: leaving {env_file} alone.{C['N']}")
        return
    if not env_file.exists():
        print(
            f"{C['Y']}Skipping .env update: {env_file} not found "
            f"(install claude-free first).{C['N']}"
        )
        return
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
            return
    for k in ("MODEL_OPUS", "MODEL_SONNET", "MODEL_HAIKU", "MODEL"):
        write_env_key(env_file, k, proxy_value)
    print(f"{C['G']}Updated {env_file}.{C['N']}")
    print(
        f"{C['D']}Restart any running proxy: `claude-free stop && claude-free` "
        f"to pick up the new tier mapping.{C['N']}"
    )


def _early_exit_path(
    args: argparse.Namespace,
    provider: Provider,
    candidates: list[str],
    limiter: Optional[RateLimiter],
    env_file: Path,
    C: dict[str, str],
) -> int:
    """Quality-priority walk: stop at first model whose TTFT <= threshold."""
    threshold = args.threshold if args.threshold > 0 else 1000.0
    measured_timeout = (threshold / 1000.0) + 0.5
    warmup_timeout = max(measured_timeout * 5, 10.0)
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
            provider, m, ee_runs, measured_timeout,
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
    proxy_value = winner if winner.startswith(provider.proxy_value_prefix) else f"{provider.proxy_value_prefix}{winner}"
    print(
        f"\n{C['B']}Picked:{C['N']} {C['G']}{winner}{C['N']}  "
        f"(TTFT {winner_record['ttft_ms']} ms, code {winner_record.get('code_score')}, "
        f"src {winner_record.get('code_src', '?')})"
    )
    print(f"  -> {proxy_value}")
    _maybe_write_env(args, env_file, proxy_value, C)
    return 0


def _full_sweep_path(
    args: argparse.Namespace,
    provider: Provider,
    candidates: list[str],
    limiter: Optional[RateLimiter],
    env_file: Path,
    C: dict[str, str],
) -> int:
    """Probe every candidate, print three rankings (TTFT / code / combined)."""
    runs = max(1, args.runs)
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
        print(f"  {m:<{width}}  ", end="", flush=True)
        r = measure(
            provider, m, runs, args.timeout,
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

    def _print_ranking(title, sorted_list, score_fn, score_label):
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
    proxy_value = winner if winner.startswith(provider.proxy_value_prefix) else f"{provider.proxy_value_prefix}{winner}"
    print(
        f"\n{C['B']}Winner ({ranking_used}):{C['N']} {C['G']}{winner}{C['N']}  "
        f"-> {proxy_value}"
    )
    _maybe_write_env(args, env_file, proxy_value, C)
    return 0


def run_audit(args: argparse.Namespace, provider: Provider) -> int:
    """Entry point for `claude-free audit` and `claude-free calibrate`."""
    C = colors()
    env_file = Path(args.env_file) if args.env_file else env_path()
    limiter = RateLimiter(args.rate) if args.rate and args.rate > 0 else None

    print(f"{C['B']}claude-free audit{C['N']}  {C['D']}-- ranking {provider.name} chat models by TTFT and code benchmarks{C['N']}\n")
    if limiter is not None:
        print(f"  {C['D']}rate limit: {args.rate:.0f} req/min sliding window (sleep before bursts){C['N']}")

    print(f"  fetching model catalogue from {provider.api_base}/models ...", end=" ", flush=True)
    try:
        available = provider.list_models()
    except Exception as e:  # noqa: BLE001
        print(f"{C['R']}failed{C['N']}: {e}")
        return 1
    print(f"{C['G']}{len(available)} models{C['N']}")

    candidates = select_candidates(args, available)
    if not candidates:
        print(f"{C['Y']}No matching models. Try --all or --filter <substr>.{C['N']}")
        return 1

    if args.early_exit:
        return _early_exit_path(args, provider, candidates, limiter, env_file, C)
    return _full_sweep_path(args, provider, candidates, limiter, env_file, C)
