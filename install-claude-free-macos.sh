#!/usr/bin/env bash
# install-claude-free-macos.sh — one-shot installer for `claude-free` on
# macOS (Apple Silicon / M-series).
#
# Sets up Claude Code routed through the free-claude-code NVIDIA NIM proxy,
# with all tiers (Opus / Sonnet / Haiku / fallback) mapped to MiniMax M2.5.
#
# Usage:
#   bash ~/install-claude-free-macos.sh
#
# Idempotent — re-running it skips steps that are already done.

set -euo pipefail

B=$'\033[1m'; R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; D=$'\033[2m'; N=$'\033[0m'

step() { printf "\n${B}==> %s${N}\n" "$*"; }
ok()   { printf "${G} OK${N}  %s\n" "$*"; }
warn() { printf "${Y}WARN${N}  %s\n" "$*"; }
err()  { printf "${R}ERR${N}  %s\n" "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

REPO="$HOME/free-claude-code"
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# ----------------------------------------------------------------------------
step "0/8  Detecting platform"
ARCH=$(uname -m)
OS=$(uname -s)
if [ "$OS" != "Darwin" ]; then
  err "this installer is for macOS — you're on $OS. Use install-claude-free.sh for Ubuntu/WSL."
  exit 1
fi
case "$ARCH" in
  arm64)  BREW_PREFIX="/opt/homebrew" ; FZF_ASSET="fzf-0.55.0-darwin_arm64.tar.gz" ;;
  x86_64) BREW_PREFIX="/usr/local"    ; FZF_ASSET="fzf-0.55.0-darwin_amd64.tar.gz" ;;
  *) err "unsupported macOS arch: $ARCH"; exit 1 ;;
esac
echo "  macOS / $ARCH (brew prefix: $BREW_PREFIX)"
ok "platform OK"

# ----------------------------------------------------------------------------
step "1/8  Homebrew + system tools (git, python3)"
if ! have brew; then
  echo "Homebrew not found. Install it interactively first:"
  echo
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  echo
  echo "Then re-run this installer."
  exit 1
fi
# Make sure brew is on PATH for this script run
export PATH="$BREW_PREFIX/bin:$PATH"

# git is usually present (Xcode CLT). python3 is usually missing.
for pkg in git python@3.12; do
  short="${pkg##*/}"; short="${short%@*}"
  if ! have "$short" && ! brew list --formula 2>/dev/null | grep -q "^${short}$"; then
    echo "Installing $pkg via brew..."
    brew install "$pkg"
  fi
done
have python3 || { err "python3 not on PATH after brew install"; exit 1; }
ok "system tools present"

# ----------------------------------------------------------------------------
step "2/8  NVIDIA API key"
if [ -f "$REPO/.env" ] && grep -qE '^NVIDIA_NIM_API_KEY="?nvapi-' "$REPO/.env"; then
  EXISTING_KEY=$(grep -E '^NVIDIA_NIM_API_KEY=' "$REPO/.env" | sed -E 's/^NVIDIA_NIM_API_KEY="?([^"]*)"?/\1/' | head -1)
  echo "Existing key found in $REPO/.env (${EXISTING_KEY:0:12}...)"
  read -r -p "Reuse it? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]$ ]]; then
    NVAPI_KEY="$EXISTING_KEY"
  else
    NVAPI_KEY=""
  fi
else
  NVAPI_KEY=""
fi
if [ -z "${NVAPI_KEY:-}" ]; then
  echo "Get a free key at: https://build.nvidia.com/settings/api-keys"
  echo "(developer tier — no credit card, ~40 req/min)"
  read -r -p "Paste your NVIDIA API key (nvapi-...): " NVAPI_KEY
fi
[ -n "$NVAPI_KEY" ] || { err "no key entered"; exit 1; }
[[ "$NVAPI_KEY" == nvapi-* ]] || warn "key does not start with 'nvapi-' — continuing anyway"
ok "key captured"

# ----------------------------------------------------------------------------
step "3/8  uv (Python package manager)"
if ! have uv; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$LOCAL_BIN:$PATH"
have uv || { err "uv not on PATH after install"; exit 1; }
uv --version
ok "uv ready"

# ----------------------------------------------------------------------------
step "4/8  Claude Code"
if ! have claude; then
  curl -fsSL https://claude.ai/install.sh | bash
fi
export PATH="$LOCAL_BIN:$PATH"
if ! have claude; then
  err "claude install failed; try manually: curl -fsSL https://claude.ai/install.sh | bash"
  exit 1
fi
claude --version || true
ok "claude ready"

# ----------------------------------------------------------------------------
step "5/8  fzf (model picker dependency)"
if ! have fzf; then
  TMP=$(mktemp -d)
  curl -fsSL "https://github.com/junegunn/fzf/releases/download/v0.55.0/$FZF_ASSET" \
    -o "$TMP/fzf.tgz"
  tar -xzf "$TMP/fzf.tgz" -C "$TMP"
  mv "$TMP/fzf" "$LOCAL_BIN/fzf"
  chmod +x "$LOCAL_BIN/fzf"
  # Apple Gatekeeper: clear quarantine so the binary runs
  xattr -d com.apple.quarantine "$LOCAL_BIN/fzf" 2>/dev/null || true
  rm -rf "$TMP"
fi
"$LOCAL_BIN/fzf" --version
ok "fzf ready"

# ----------------------------------------------------------------------------
step "6/8  Cloning free-claude-code + installing Python deps"
if [ ! -d "$REPO/.git" ]; then
  git clone https://github.com/Alishahryar1/free-claude-code.git "$REPO"
else
  echo "repo already at $REPO — skipping clone"
fi
cd "$REPO"

uv python install 3.14 >/dev/null 2>&1 || true
echo "Running uv sync (this may take a minute on first run)..."
uv sync --quiet || uv sync

# fetch NVIDIA models catalog (powers `claude-free pick`)
if [ ! -s "$REPO/nvidia_nim_models.json" ]; then
  curl -fsSL "https://integrate.api.nvidia.com/v1/models" \
    -H "Authorization: Bearer $NVAPI_KEY" \
    -o "$REPO/nvidia_nim_models.json" \
    || warn "couldn't fetch nvidia_nim_models.json (model picker won't work until you do)"
fi
ok "repo ready"

# ----------------------------------------------------------------------------
step "7/8  Writing $REPO/.env (tiers: all MiniMax M2.5)"
[ -f "$REPO/.env" ] || cp "$REPO/.env.example" "$REPO/.env"

# In-place key=value setter (Python = portable, handles quoting)
setenv() {
  python3 - "$REPO/.env" "$1" "$2" <<'PY'
import re, sys
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f: txt = f.read()
line = f'{key}="{val}"'
if re.search(rf'^{re.escape(key)}=', txt, flags=re.M):
    txt = re.sub(rf'^{re.escape(key)}=.*$', line, txt, flags=re.M)
else:
    if not txt.endswith('\n'): txt += '\n'
    txt += line + '\n'
with open(path, 'w') as f: f.write(txt)
PY
}

setenv NVIDIA_NIM_API_KEY    "$NVAPI_KEY"
setenv ANTHROPIC_AUTH_TOKEN  "freecc"
setenv MODEL_OPUS            "nvidia_nim/minimaxai/minimax-m2.5"
setenv MODEL_SONNET          "nvidia_nim/minimaxai/minimax-m2.5"
setenv MODEL_HAIKU           "nvidia_nim/minimaxai/minimax-m2.5"
setenv MODEL                 "nvidia_nim/minimaxai/minimax-m2.5"
ok ".env configured"

# ----------------------------------------------------------------------------
step "8/8  Installing claude-free launcher to $LOCAL_BIN/claude-free"
cat > "$LOCAL_BIN/claude-free" <<'CLAUDE_FREE_EOF'
#!/usr/bin/env bash
# claude-free — launch Claude Code through the free-claude-code NVIDIA NIM proxy.
#
# Subcommands:
#   claude-free [args...]   start proxy if needed, launch claude (default model from .env)
#   claude-free pick        interactive NVIDIA NIM model picker (fzf), then launch
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
  claude-free [args...]   start proxy if needed, launch claude (passes args through)
  claude-free pick        interactive NVIDIA NIM model picker (fzf), then launch
  claude-free rate        show NVIDIA rate-limit hits from proxy log (replaces /usage)
  claude-free logs        tail the proxy log
  claude-free status      check whether proxy is running and show /model tier mapping
  claude-free models      same as status — the /model tier -> NVIDIA model mapping
  claude-free stop        kill the running proxy
  claude-free help        this help

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

case "${1:-}" in
  pick)
    shift || true
    start_proxy || exit 1
    cd "$REPO_DIR"
    exec ./claude-pick "$@"
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
CLAUDE_FREE_EOF

chmod +x "$LOCAL_BIN/claude-free"
ok "claude-free installed"

# ----------------------------------------------------------------------------
step "Final  PATH check (zsh + bash)"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
  if [ -f "$rc" ] || [ "${rc##*/}" = ".zshrc" ]; then
    if ! grep -q '\.local/bin' "$rc" 2>/dev/null; then
      printf '\n# Added by install-claude-free-macos.sh\n%s\n' "$PATH_LINE" >> "$rc"
      warn "appended PATH to $rc"
    fi
  fi
done

# ----------------------------------------------------------------------------
echo
printf "${G}============================================================${N}\n"
printf "${G}  Installation complete!${N}\n"
printf "${G}============================================================${N}\n"
echo
echo "  Open a new terminal (or: ${D}source ~/.zshrc${N}) then run:"
echo
echo "  Run Claude Code with NVIDIA NIM:   ${B}claude-free${N}"
echo "  Show active model mapping:         ${B}claude-free models${N}"
echo "  Switch model interactively:        ${B}claude-free pick${N}"
echo "  Show rate-limit usage:             ${B}claude-free rate${N}"
echo "  Stop the proxy:                    ${B}claude-free stop${N}"
echo "  Help:                              ${B}claude-free help${N}"
echo
echo "  Config file:  ${D}~/free-claude-code/.env${N}"
echo "  Proxy log:    ${D}~/free-claude-code/claude-free-proxy.log${N}"
echo
