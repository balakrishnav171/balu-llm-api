#!/usr/bin/env bash
# =============================================================================
# startup.sh — Balu LLM API startup script
#
# Validates required environment variables, then launches the API server
# with uvicorn.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'   # No colour

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Load .env if present (and not already set by the container runtime)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
    info "Loading environment from ${ENV_FILE}"
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
else
    warn ".env file not found — relying on pre-set environment variables."
fi

# ---------------------------------------------------------------------------
# Required variable checks
# ---------------------------------------------------------------------------
MISSING=()

check_required() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        MISSING+=("$var_name")
    fi
}

check_required "API_KEY"

# Backend-specific checks
LLM_BACKEND="${LLM_BACKEND:-ollama}"

if [[ "${LLM_BACKEND}" == "azure_openai" ]]; then
    check_required "AZURE_OPENAI_ENDPOINT"
    check_required "AZURE_OPENAI_KEY"
    check_required "AZURE_OPENAI_DEPLOYMENT"
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    error "The following required environment variables are not set:"
    for var in "${MISSING[@]}"; do
        error "  - ${var}"
    done
    die "Please set the missing variables (see .env.example) and retry."
fi

# ---------------------------------------------------------------------------
# Warn about insecure default API key
# ---------------------------------------------------------------------------
if [[ "${API_KEY}" == "your-secret-api-key-here" ]]; then
    warn "API_KEY is set to the default placeholder value — change it before exposing this service!"
fi

# ---------------------------------------------------------------------------
# Display startup summary
# ---------------------------------------------------------------------------
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"

info "====================================================="
info " Balu LLM API"
info "====================================================="
info " Backend   : ${LLM_BACKEND}"

if [[ "${LLM_BACKEND}" == "ollama" ]]; then
    info " Ollama URL: ${OLLAMA_BASE_URL:-http://localhost:11434}"
    info " Model     : ${OLLAMA_MODEL:-orca-mini}"
else
    info " Azure EP  : ${AZURE_OPENAI_ENDPOINT}"
    info " Deployment: ${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}"
fi

info " Host      : ${HOST}:${PORT}"
info " Workers   : ${WORKERS}"
info " Log level : ${LOG_LEVEL}"
info "====================================================="

# ---------------------------------------------------------------------------
# Optional: pre-flight connectivity check for Ollama
# ---------------------------------------------------------------------------
if [[ "${LLM_BACKEND}" == "ollama" ]]; then
    OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
    info "Checking Ollama connectivity at ${OLLAMA_URL} …"

    if command -v curl &>/dev/null; then
        if curl -sf "${OLLAMA_URL}/api/tags" -o /dev/null; then
            info "Ollama is reachable."
        else
            warn "Ollama did not respond — the API will start but /v1/chat may fail until Ollama is up."
        fi
    else
        warn "curl not found — skipping Ollama pre-flight check."
    fi
fi

# ---------------------------------------------------------------------------
# Launch uvicorn
# ---------------------------------------------------------------------------
info "Starting uvicorn …"

exec uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL,,}" \
    --log-config /dev/null    # suppress uvicorn's default logging (we use JSON)
