#!/usr/bin/env bash
# =============================================================================
# run.sh — Genesis Microservices Generator
# Single-command, logically-gated build-and-run script.
#
# Usage:
#   ./run.sh              # build + start (default)
#   ./run.sh --stop       # stop all services and remove containers
#   ./run.sh --clean      # stop + remove volumes + prune build cache
#   ./run.sh --logs       # tail live logs from running stack
#   ./run.sh --status     # print container health status
#   ./run.sh --help       # this message
# =============================================================================
set -euo pipefail
IFS=$'\n\t'

# ── Colours ──────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
ts()   { date '+%H:%M:%S'; }
info() { echo -e "${CYAN}[$(ts)] ▸ $*${RESET}"; }
ok()   { echo -e "${GREEN}[$(ts)] ✓ $*${RESET}"; }
warn() { echo -e "${YELLOW}[$(ts)] ⚠ $*${RESET}"; }
die()  { echo -e "${RED}[$(ts)] ✗ $*${RESET}" >&2; exit 1; }
hr()   { echo -e "${BOLD}────────────────────────────────────────────────────────────${RESET}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PORT=8001
MONGO_PORT=27017
HEALTH_TIMEOUT=120   # seconds to wait for healthy stack
COMPOSE_PROJECT="genesis"

# Detect `docker compose` (v2 plugin) vs legacy `docker-compose`
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose &>/dev/null; then
  DC="docker-compose"
else
  DC=""
fi

# ── Sub-commands ─────────────────────────────────────────────────────────────
cmd_stop() {
  info "Stopping Genesis stack…"
  cd "$SCRIPT_DIR"
  $DC -p "$COMPOSE_PROJECT" down --remove-orphans
  ok "Stack stopped."
}

cmd_clean() {
  info "Cleaning Genesis stack (containers + volumes + build cache)…"
  cd "$SCRIPT_DIR"
  $DC -p "$COMPOSE_PROJECT" down --remove-orphans --volumes
  docker builder prune -f --filter label=project=genesis 2>/dev/null || true
  ok "Clean complete."
}

cmd_logs() {
  cd "$SCRIPT_DIR"
  $DC -p "$COMPOSE_PROJECT" logs --follow --tail=100
}

cmd_status() {
  cd "$SCRIPT_DIR"
  $DC -p "$COMPOSE_PROJECT" ps
}

cmd_help() {
  sed -n '3,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ── Parse arguments ───────────────────────────────────────────────────────────
case "${1:-}" in
  --stop)   cmd_stop;   exit 0 ;;
  --clean)  cmd_clean;  exit 0 ;;
  --logs)   cmd_logs;   exit 0 ;;
  --status) cmd_status; exit 0 ;;
  --help|-h) cmd_help;  exit 0 ;;
  "")       : ;;   # default: build + run
  *) die "Unknown argument: $1  (run with --help for usage)" ;;
esac

# ── Failure trap ──────────────────────────────────────────────────────────────
_on_error() {
  local exit_code=$?
  echo
  die "Build/start failed at line ${BASH_LINENO[0]} (exit $exit_code). Run './run.sh --logs' to inspect."
}
trap '_on_error' ERR

# =============================================================================
# GATE 0 — Preflight: environment & tool checks
# =============================================================================
hr
echo -e "${BOLD}  Genesis Microservices Generator — Build & Run${RESET}"
hr

info "Gate 0 — Preflight checks"

# Bash version
[[ "${BASH_VERSINFO[0]}" -ge 4 ]] \
  || die "Bash 4+ required (found $BASH_VERSION). On macOS: brew install bash"
ok "Bash $BASH_VERSION"

# OS
OS_TYPE="$(uname -s)"
ok "OS: $OS_TYPE"

# Docker daemon
if ! docker info &>/dev/null; then
  die "Docker daemon is not running. Start Docker Desktop or 'sudo systemctl start docker' and retry."
fi
DOCKER_VERSION="$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
ok "Docker daemon running (server $DOCKER_VERSION)"

# docker compose
[[ -n "$DC" ]] \
  || die "Neither 'docker compose' (v2 plugin) nor 'docker-compose' found. Install Docker Compose and retry."
COMPOSE_VERSION="$($DC version --short 2>/dev/null || $DC version 2>/dev/null | head -1)"
ok "Compose: $DC  ($COMPOSE_VERSION)"

# =============================================================================
# GATE 1 — Repo integrity: all required paths must exist
# =============================================================================
info "Gate 1 — Repository integrity"

cd "$SCRIPT_DIR"

declare -A REQUIRED_PATHS=(
  ["Dockerfile"]="top-level Dockerfile"
  ["docker-compose.yml"]="Compose file"
  ["genesis.py"]="Genesis generator"
  ["service-spec.yaml"]="example service spec"
  ["backend/server.py"]="FastAPI server"
  ["backend/requirements.txt"]="Python requirements"
  ["backend/generator/engine.py"]="generator engine"
  ["backend/generator/models.py"]="generator models"
  ["frontend/package.json"]="frontend package manifest"
  ["frontend/public/index.html"]="frontend HTML entry"
  ["frontend/src/index.js"]="frontend JS entry"
)

MISSING=0
for path in "${!REQUIRED_PATHS[@]}"; do
  if [[ ! -e "$SCRIPT_DIR/$path" ]]; then
    warn "Missing: $path  (${REQUIRED_PATHS[$path]})"
    (( MISSING++ )) || true
  fi
done

[[ $MISSING -eq 0 ]] || die "$MISSING required file(s) missing. Ensure you cloned the full repository."
ok "All required files present (${#REQUIRED_PATHS[@]} checks passed)"

# =============================================================================
# GATE 2 — Port availability
# =============================================================================
info "Gate 2 — Port availability"

check_port() {
  local port=$1 label=$2
  if (echo "" 2>/dev/null >/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
    warn "Port $port ($label) appears to be in use."
    warn "Another process may already be running. Attempting to continue…"
    warn "If the build fails, stop whatever is using port $port and retry."
  else
    ok "Port $port ($label) is free"
  fi
}

check_port "$APP_PORT"   "app"
check_port "$MONGO_PORT" "mongodb"

# =============================================================================
# GATE 3 — Build
# =============================================================================
info "Gate 3 — docker compose build"

$DC -p "$COMPOSE_PROJECT" build --progress=plain \
  || die "Build failed. Review the output above for errors."

ok "Images built successfully"

# =============================================================================
# GATE 4 — Launch + health wait
# =============================================================================
info "Gate 4 — Starting stack (app + MongoDB)"

$DC -p "$COMPOSE_PROJECT" up -d --remove-orphans

info "Waiting up to ${HEALTH_TIMEOUT}s for all services to become healthy…"

ELAPSED=0
INTERVAL=5
ALL_HEALTHY=false

while [[ $ELAPSED -lt $HEALTH_TIMEOUT ]]; do
  sleep $INTERVAL
  (( ELAPSED += INTERVAL )) || true

  # Count running containers for this project
  RUNNING=$($DC -p "$COMPOSE_PROJECT" ps --status running --quiet 2>/dev/null | wc -l | tr -d ' ')
  TOTAL=$($DC -p "$COMPOSE_PROJECT" ps --quiet 2>/dev/null | wc -l | tr -d ' ')

  # Check health status via docker inspect
  UNHEALTHY=0
  STARTING=0
  while IFS= read -r cid; do
    [[ -z "$cid" ]] && continue
    health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null)"
    case "$health" in
      unhealthy) (( UNHEALTHY++ )) || true ;;
      starting)  (( STARTING++  )) || true ;;
    esac
  done < <($DC -p "$COMPOSE_PROJECT" ps --quiet 2>/dev/null)

  if [[ $UNHEALTHY -gt 0 ]]; then
    die "One or more containers became unhealthy. Run './run.sh --logs' for details."
  fi

  if [[ $STARTING -eq 0 && $RUNNING -eq $TOTAL && $TOTAL -gt 0 ]]; then
    ALL_HEALTHY=true
    break
  fi

  info "  ${ELAPSED}s — running: $RUNNING/$TOTAL  still-starting: $STARTING"
done

$ALL_HEALTHY || die "Stack did not become healthy within ${HEALTH_TIMEOUT}s. Run './run.sh --logs' to diagnose."
ok "All $TOTAL containers running and healthy (${ELAPSED}s)"

# =============================================================================
# GATE 5 — Smoke tests
# =============================================================================
info "Gate 5 — HTTP smoke tests"

smoke_get() {
  local label=$1 url=$2 expected_substr=$3
  local response http_code body

  # retry up to 10 times (the app process may still be binding inside the container)
  local attempt=0
  while [[ $attempt -lt 10 ]]; do
    http_code=$(curl -s -o /tmp/genesis_smoke_body -w "%{http_code}" \
      --connect-timeout 3 --max-time 8 "$url" 2>/dev/null || echo "000")
    body=$(cat /tmp/genesis_smoke_body 2>/dev/null || true)

    if [[ "$http_code" == "200" ]]; then
      if [[ -n "$expected_substr" ]] && ! echo "$body" | grep -q "$expected_substr"; then
        die "Smoke test '$label': HTTP 200 but response did not contain '$expected_substr'"
      fi
      ok "Smoke: $label → HTTP $http_code ✓"
      return 0
    fi

    (( attempt++ )) || true
    sleep 3
  done

  die "Smoke test '$label' failed: HTTP $http_code (expected 200) after $attempt attempts.\nURL: $url\nRun './run.sh --logs' for details."
}

BASE="http://localhost:${APP_PORT}"
smoke_get "API root"         "${BASE}/api/"              "Hello World"
smoke_get "Generator info"   "${BASE}/api/generator/info" "genesis"

# =============================================================================
# SUCCESS
# =============================================================================
hr
echo -e "${GREEN}${BOLD}"
echo "  ✓  Genesis Microservices Generator is UP"
echo ""
echo "     App  →  http://localhost:${APP_PORT}"
echo "     API  →  http://localhost:${APP_PORT}/api/"
echo "     Docs →  http://localhost:${APP_PORT}/api/docs"
echo ""
echo "  ./run.sh --logs    stream live logs"
echo "  ./run.sh --status  container health status"
echo "  ./run.sh --stop    stop the stack"
echo "  ./run.sh --clean   stop + remove volumes + cache"
echo -e "${RESET}"
hr
