#!/usr/bin/env bash
# claude-free — launch Claude Code through the free-claude-code NVIDIA NIM proxy.
#
# Subcommands:
#   claude-free [args...]   start proxy if needed, launch claude (default model from .env)
#   claude-free pick        interactive NVIDIA NIM model picker (fzf), then launch
#   claude-free audit       probe NVIDIA NIM models for TTFT + code benchmarks, rank them
#   claude-free calibrate   walk models by code-score, pick first with TTFT <= 1s, set .env
#   claude-free update      refresh the audit script + benchmarks table from GitHub
#   claude-free rate        show NVIDIA rate-limit hits from proxy log (replaces /usage)
#   claude-free logs        tail the proxy log
#   claude-free status      check whether proxy is running and show current model
#   claude-free stop        kill the running proxy
#   claude-free help        this help

set -euo pipefail

REPO_DIR="$HOME/free-claude-code"
PORT=8082
LOG_FILE="$REPO_DIR/claude-free-proxy.log"
PID_FILE="$REPO_DIR/claude-free-proxy.pid"
ENV_FILE="$REPO_DIR/.env"

B=$'\033[1m'; R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; D=$'\033[2m'; N=$'\033[0m'

read_env() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  local raw
  raw="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$ENV_FILE" | tail -n 1 || true)"
  raw="${raw#*=}"
  raw="${raw%%#*}"
  raw="$(echo "$raw" | xargs || true)"
  raw="${raw%\"}"; raw="${raw#\"}"; raw="${raw%\'}"; raw="${raw#\'}"
  echo "$raw"
}

is_proxy_up() {
  # Subshell wrap for /dev/tcp — on macOS bash 3.2 the shell prints
  # "connect: Connection refused" to stderr on a failed redirect even
  # with 2>/dev/null. Subshell + outer redirect catches it cleanly.
  ( : </dev/tcp/127.0.0.1/"$PORT" ) >/dev/null 2>&1 && return 0
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1 && return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import socket,sys
s=socket.socket(); s.settimeout(0.5)
try: s.connect(('127.0.0.1', $PORT)); s.close()
except Exception: sys.exit(1)" >/dev/null 2>&1 && return 0
  fi
  return 1
}

start_proxy() {
  if is_proxy_up; then
    echo "${D}proxy already up on :$PORT${N}" >&2
    return 0
  fi
  cd "$REPO_DIR"
  echo "${D}starting proxy on :$PORT (log: $LOG_FILE)${N}" >&2
  nohup uv run uvicorn server:app --host 127.0.0.1 --port "$PORT" \
    >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  for i in $(seq 1 80); do
    sleep 0.25
    if is_proxy_up; then
      echo "${G}proxy ready${N}" >&2
      return 0
    fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "${R}proxy died during startup. tail of log:${N}" >&2
      tail -n 30 "$LOG_FILE" >&2
      return 1
    fi
  done
  echo "${R}proxy failed to start in 20s. tail of log:${N}" >&2
  tail -n 30 "$LOG_FILE" >&2
  return 1
}

stop_proxy() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
      echo "${G}stopped pid $pid${N}" >&2
    fi
    rm -f "$PID_FILE"
  fi
  pkill -f "uvicorn server:app.*--port $PORT" 2>/dev/null || true
}

show_rate() {
  echo "${B}claude-free :: NVIDIA rate-limit view${N}"
  echo "${D}log: $LOG_FILE${N}"
  echo
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "${Y}no proxy log yet — run \`claude-free\` first.${N}"
    return 0
  fi
  local total_429 total_5xx total_requests
  total_429=$(grep -ciE "(429|rate.?limit|too many requests)" "$LOG_FILE" 2>/dev/null || echo 0)
  total_5xx=$(grep -cE "HTTP/1\.[01]\" 5[0-9][0-9]| 5[0-9][0-9] " "$LOG_FILE" 2>/dev/null || echo 0)
  total_requests=$(grep -cE "POST .*(messages|completions)" "$LOG_FILE" 2>/dev/null || echo 0)
  printf "  log lines             : %s\n" "$(wc -l < "$LOG_FILE")"
  printf "  request lines         : %s\n" "$total_requests"
  printf "  ${Y}rate-limit (429) hits : %s${N}\n" "$total_429"
  printf "  5xx errors            : %s\n" "$total_5xx"
  if [[ "$total_429" -gt 0 ]]; then
    echo
    echo "${B}last 5 rate-limit lines:${N}"
    grep -niE "(429|rate.?limit|too many requests)" "$LOG_FILE" | tail -n 5 | sed 's/^/  /'
  fi
  echo
  echo "${B}configured proxy throttle (.env):${N}"
  for k in PROVIDER_RATE_LIMIT PROVIDER_RATE_WINDOW PROVIDER_MAX_CONCURRENCY; do
    v="$(read_env "$k")"
    printf "  %-26s = %s\n" "$k" "${v:-<unset>}"
  done
  echo
  echo "${D}NVIDIA NIM free tier is typically ~40 req/min per key. The built-in /usage${N}"
  echo "${D}slash command shows fake numbers under the proxy — use this view instead.${N}"
}

print_help() {
  cat <<HELP
${B}claude-free${N} — Claude Code via the free-claude-code NVIDIA NIM proxy

${B}usage:${N}
  ${B}claude-free${N} [args...]    start proxy if needed, launch claude (passes args through)
  ${B}claude-free pick${N}         interactive NVIDIA NIM model picker (fzf), then launch
  ${B}claude-free audit${N}        probe NIM chat models for TTFT + code benchmarks, rank them
                          flags: --all  --filter <s>  --include <id>  --runs N
                                 --by {combined,ttft,code}  --tau MS  --rate REQ_MIN
                                 --early-exit  --threshold MS  --set  --no-set
  ${B}claude-free calibrate${N}    walk models by code-score, pick the first with TTFT <= 1s
                          and write it to .env. takes the same flags as audit, e.g.:
                            claude-free calibrate --threshold 500
                            claude-free calibrate --filter qwen
  ${B}claude-free update${N}       refresh ~/.local/bin/claude-free-audit.py from GitHub
                          (gets you new models + updated benchmark scores)
  ${B}claude-free rate${N}         show NVIDIA rate-limit hits from proxy log (replaces /usage)
  ${B}claude-free logs${N}         tail the proxy log
  ${B}claude-free status${N}       check whether proxy is running and show /model tier mapping
  ${B}claude-free models${N}       same as status — the /model tier -> NVIDIA model mapping
  ${B}claude-free stop${N}         kill the running proxy
  ${B}claude-free help${N}         this help

${B}config:${N} $ENV_FILE
${B}log:${N}    $LOG_FILE

Sessions, history, projects, settings and memory are shared with native ${B}claude${N}
because both use the same \$HOME/.claude/ directory.
HELP
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "${R}no .env at $ENV_FILE — clone Alishahryar1/free-claude-code first${N}" >&2
  exit 1
fi
KEY="$(read_env NVIDIA_NIM_API_KEY)"
if [[ -z "$KEY" ]]; then
  echo "${R}NVIDIA_NIM_API_KEY is empty in $ENV_FILE — fill it in and try again${N}" >&2
  exit 1
fi
TOKEN="$(read_env ANTHROPIC_AUTH_TOKEN)"
TOKEN="${TOKEN:-freecc}"

AUDIT_SCRIPT="$HOME/.local/bin/claude-free-audit.py"

case "${1:-}" in
  pick)
    shift || true
    start_proxy || exit 1
    cd "$REPO_DIR"
    exec ./claude-pick "$@"
    ;;
  audit)
    shift || true
    if [[ ! -f "$AUDIT_SCRIPT" ]]; then
      echo "${R}audit script missing at $AUDIT_SCRIPT${N}" >&2
      echo "${D}re-run the installer or fetch:${N}" >&2
      echo "  curl -fsSL https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py -o '$AUDIT_SCRIPT'" >&2
      exit 1
    fi
    exec python3 "$AUDIT_SCRIPT" "$@"
    ;;
  calibrate)
    shift || true
    if [[ ! -f "$AUDIT_SCRIPT" ]]; then
      echo "${R}audit script missing at $AUDIT_SCRIPT${N}" >&2
      echo "${D}fix: claude-free update${N}" >&2
      exit 1
    fi
    # `calibrate` = walk benchmarked models top-down by code-score, pick the
    # first one whose TTFT is <= 1000ms, write it to .env. Forwards extras so
    # the user can still pass --threshold / --filter / --runs etc.
    exec python3 "$AUDIT_SCRIPT" --set --early-exit --threshold 1000 "$@"
    ;;
  update)
    shift || true
    URL="https://raw.githubusercontent.com/ChenghengLi/claude-free-installer/main/claude-free-audit.py"
    echo "${B}claude-free update${N}  ${D}— refreshing audit script + benchmarks table${N}"
    echo "  fetching $URL"
    if curl -fsSL "$URL" -o "$AUDIT_SCRIPT.new"; then
      mv "$AUDIT_SCRIPT.new" "$AUDIT_SCRIPT"
      chmod +x "$AUDIT_SCRIPT" 2>/dev/null || true
      echo "${G}updated $AUDIT_SCRIPT${N}"
    else
      rm -f "$AUDIT_SCRIPT.new"
      echo "${R}fetch failed — keeping existing script${N}" >&2
      exit 1
    fi
    ;;
  rate|usage|limits)
    show_rate
    ;;
  logs|log)
    [[ -f "$LOG_FILE" ]] || { echo "no log yet"; exit 0; }
    exec tail -n 80 -f "$LOG_FILE"
    ;;
  stop|kill)
    stop_proxy
    ;;
  status|models)
    if is_proxy_up; then
      echo "${G}proxy up on :$PORT${N}"
      [[ -f "$PID_FILE" ]] && echo "  pid: $(cat "$PID_FILE")"
    else
      echo "${Y}proxy not running${N}"
    fi
    echo
    echo "${B}/model tier mapping (what each Claude Code label actually runs):${N}"
    printf "  %-9s %s -> ${G}%s${N}\n" "Opus"   "(label: 'Opus 4.7')"  "$(read_env MODEL_OPUS)"
    printf "  %-9s %s -> ${G}%s${N}\n" "Sonnet" "(label: 'Sonnet 4.6')" "$(read_env MODEL_SONNET)"
    printf "  %-9s %s -> ${G}%s${N}\n" "Haiku"  "(label: 'Haiku 4.5')"  "$(read_env MODEL_HAIKU)"
    printf "  %-9s %-22s -> ${G}%s${N}\n" "Fallback" "(MODEL=)"           "$(read_env MODEL)"
    echo
    echo "${D}Claude Code's /model labels (Sonnet 4.6, Opus 4.7, Haiku 4.5) are hardcoded${N}"
    echo "${D}into the client and cannot be relabeled — only the routing is overridden.${N}"
    echo "${D}Edit ~/free-claude-code/.env to change tiers; \`claude-free pick\` for full picker.${N}"
    ;;
  help|-h|--help-claude-free)
    print_help
    ;;
  *)
    start_proxy || exit 1
    export ANTHROPIC_BASE_URL="http://localhost:$PORT"
    export ANTHROPIC_AUTH_TOKEN="$TOKEN"
    echo
    echo "${B}claude-free${N} via NVIDIA NIM (free) — /model tiers route to:"
    printf "  Opus   -> ${G}%s${N}\n"  "$(read_env MODEL_OPUS)"
    printf "  Sonnet -> ${G}%s${N}  ${D}(default)${N}\n" "$(read_env MODEL_SONNET)"
    printf "  Haiku  -> ${G}%s${N}\n"  "$(read_env MODEL_HAIKU)"
    echo "${D}(run \`claude-free models\` anytime to recheck; \`claude-free pick\` to switch.)${N}"
    echo
    exec claude "$@"
    ;;
esac
