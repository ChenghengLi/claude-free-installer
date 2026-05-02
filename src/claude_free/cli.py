"""Argument parsing + top-level dispatch.

Public entry point: `main(argv: list[str]) -> int`.
"""

from __future__ import annotations

import argparse
import sys

from claude_free import __version__
from claude_free.commands.audit import run_audit
from claude_free.commands.update import run_update
from claude_free.env import resolve_api_key
from claude_free.providers import get_provider, register_providers


def _build_audit_parser(p: argparse.ArgumentParser) -> None:
    """Add the audit/calibrate flags. calibrate is `audit --set --early-exit`."""
    p.add_argument("--all", action="store_true", help="probe every chat-capable model in your account")
    p.add_argument("--filter", default="", help="only probe model ids containing this substring")
    p.add_argument("--include", action="append", default=[], help="add a specific model id (repeatable)")
    p.add_argument("--runs", type=int, default=3, help="measured runs per model after 1 warmup (default 3)")
    p.add_argument("--timeout", type=float, default=45.0, help="per-probe timeout in seconds (default 45)")
    p.add_argument("--max", type=int, default=15, help="max number of models to probe (default 15)")
    p.add_argument("--no-warmup", action="store_true", help="skip the warmup probe")
    p.add_argument(
        "--by",
        choices=("smart", "combined", "ttft", "code"),
        default="smart",
        help=(
            "rank winner by: smart (default, code * exp(-(TTFT + output/tok_per_s) / tau)), "
            "combined (TTFT-only variant), ttft (fastest), or code (best benchmarks)"
        ),
    )
    p.add_argument(
        "--tau",
        type=float,
        default=3000.0,
        help="latency penalty constant in ms (default 3000). lower = penalize slow models harder",
    )
    p.add_argument(
        "--output-tokens",
        type=int,
        default=200,
        help="typical response length used by smart_score (default 200 tokens)",
    )
    p.add_argument(
        "--early-exit",
        action="store_true",
        help="walk every benchmarked model in code-score-desc order; stop at first model with TTFT <= --threshold",
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
        help="max requests/min to the provider (default 30; free NIM ceiling is ~40). 0 = no limit",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--set", dest="auto_set", action="store_true", help="auto-set winner to all tiers (no prompt)")
    g.add_argument("--no-set", dest="no_set", action="store_true", help="never offer to set the winner")
    p.add_argument("--key", help="provider API key (overrides env / .env)")
    p.add_argument(
        "--provider",
        default="nvidia-nim",
        choices=list(register_providers().keys()),
        help="which inference provider to probe (default: nvidia-nim)",
    )
    p.add_argument("--env-file", help="path to free-claude-code .env (default ~/free-claude-code/.env)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-free-audit",
        description="Audit, calibrate, and switch NVIDIA NIM models for Claude Code.",
    )
    p.add_argument("--version", action="version", version=f"claude-free-audit {__version__}")
    sub = p.add_subparsers(dest="command")

    p_audit = sub.add_parser(
        "audit",
        help="probe models for TTFT + code benchmarks, print three rankings",
    )
    _build_audit_parser(p_audit)

    p_calibrate = sub.add_parser(
        "calibrate",
        help="walk by code-score, pick first model with TTFT <= 1s, write to .env",
    )
    _build_audit_parser(p_calibrate)

    sub.add_parser("update", help="show how to refresh the deployed audit script")

    # Back-compat: if no subcommand, accept all the audit flags directly
    # (so `claude-free-audit.py --early-exit ...` keeps working as before
    # without an explicit `audit` subcommand).
    _build_audit_parser(p)
    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "update":
        return run_update(args, None)

    # calibrate is audit with extra defaults baked in
    if args.command == "calibrate":
        if not args.early_exit:
            args.early_exit = True
        if args.threshold == 0:
            args.threshold = 1000.0
        if not args.auto_set and not args.no_set:
            args.auto_set = True

    api_key = args.key or resolve_api_key(args.provider)
    if not api_key:
        env_var = {
            "nvidia-nim": "NVIDIA_NIM_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(args.provider, args.provider.upper().replace("-", "_") + "_API_KEY")
        print(
            f"No API key for provider '{args.provider}'. "
            f"Set ${env_var} or populate ~/free-claude-code/.env, "
            f"or pass --key.",
            file=sys.stderr,
        )
        return 2

    provider_cls = get_provider(args.provider)
    provider = provider_cls(api_key)
    return run_audit(args, provider)
