# Changelog

All notable changes to this repo. The format is loosely based on [Keep a Changelog](https://keepachangelog.com/), and the project follows pragmatic semver.

## Unreleased

- Refactor the audit script into a proper Python package under `src/claude_free/`, with a `pyproject.toml`, a build script that bundles to a single `claude-free-audit.py`, and basic tests. Plus extension points for future providers (OpenRouter, Together AI, etc.). [planned]

## 2026-05-02 — docs overhaul

- Slim README to a 1-page quick-start with install commands first.
- Add `docs/INSTALL.md`, `docs/COMMANDS.md`, `docs/AUDIT.md`, `docs/BENCHMARKS.md`, `docs/TROUBLESHOOTING.md`, `docs/FAQ.md` covering install, every subcommand, the audit/calibrate design, the benchmark methodology, runtime issues, and short answers.
- Add this CHANGELOG.

## 2026-05-02 — `audit` / `calibrate` / `update` subcommands

- New `claude-free-audit.py` (stdlib-only, ~600 lines) — probes NVIDIA NIM chat models for TTFT and ranks them by latency, code-benchmark score, or a combined "fast+good" score.
- New `claude-free audit` — full sweep, three rankings (TTFT / code / combined).
- New `claude-free calibrate` — quality-priority walk: top-down by code score, picks the first model whose TTFT clears `--threshold` (default 1000 ms), writes it to `.env`. Internally `audit --set --early-exit --threshold 1000`.
- New `claude-free update` — atomically refreshes `~/.local/bin/claude-free-audit.py` from `raw.githubusercontent.com/.../main/claude-free-audit.py`. No re-install needed for benchmark table refreshes.
- Built-in `BENCHMARKS` table — 40+ models with SWE-bench Verified / LiveCodeBench / HumanEval scores from vendor model cards and aggregator leaderboards (May 2026 snapshot).
- Built-in rate limiter — sliding-window, default 30 req/min (under NIM's ~40/min ceiling), honours `Retry-After` on 429.
- `calibrate`-specific optimizations:
  - Dynamic per-probe timeout in early-exit mode = `threshold + 0.5 s`, so a >1 s model is dropped after ~1.5 s instead of waiting the full `--timeout`.
  - Shorter warmup budget in early-exit (10 s vs 90 s) — calibrate is "fast NOW", cold huge models that need 60 s to load aren't in scope.
  - One measured run per model in early-exit (vs 3 for full audit) — one passing TTFT is enough signal.
- All three installers (Linux + macOS + Windows) updated to fetch the audit script during install and add `audit` / `calibrate` / `update` subcommand cases to their launchers.
- Help text and final-summary blocks in all three installers updated.

## 2026 (earlier — prior installer commits)

These predate the audit/calibrate work. See `git log` for full detail.

- `fix(probe): silence bash 'Connection refused' diagnostic on macOS`
- `fix(win): launcher Start-Process can't redirect stdout+stderr to same file`
- `fix(win): native-command stderr crashing PowerShell 5.1`
- `feat: add Windows (PowerShell) installer`
- Initial Ubuntu / WSL + macOS installers, `claude-free pick`, `rate`, `models`, `logs`, `stop`.
