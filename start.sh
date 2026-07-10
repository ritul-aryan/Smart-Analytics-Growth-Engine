#!/usr/bin/env bash
# =============================================================================
# start.sh — One-command local startup for MAE
#
# Usage:
#   chmod +x start.sh
#   ./start.sh
#
# What it does:
#   1. Checks .env exists (copies .env.example if not)
#   2. Creates the Python virtual environment if absent
#   3. Installs / upgrades Python dependencies
#   4. Runs Alembic migrations (creates SQLite DB on first run)
#   5. Installs frontend npm dependencies if node_modules is absent
#   6. Starts the FastAPI backend (port 8000) in the background
#   7. Starts the Vite dev server (port 5173) in the foreground
#   8. On Ctrl-C, kills both processes cleanly
#
# Requirements:
#   - Python 3.11+
#   - Node.js 18+
#   - npm 9+
# =============================================================================

set -euo pipefail

RESET='\033[0m'
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()   { echo -e "${BOLD}${CYAN}[MAE]${RESET} $*"; }
ok()    { echo -e "${BOLD}${GREEN}[MAE]${RESET} $*"; }
warn()  { echo -e "${BOLD}${YELLOW}[MAE]${RESET} $*"; }
error() { echo -e "${BOLD}${RED}[MAE]${RESET} $*" >&2; }

# -----------------------------------------------------------------------------
# 1. .env
# -----------------------------------------------------------------------------

if [ ! -f ".env" ]; then
  warn ".env not found — copying .env.example"
  cp .env.example .env
  warn "Please open .env and set GEMINI_API_KEY, then re-run ./start.sh"
  exit 1
fi

# Warn if GEMINI_API_KEY is blank and provider is gemini
if grep -qE "^LLM_PROVIDER=gemini" .env 2>/dev/null; then
  if ! grep -qE "^GEMINI_API_KEY=.+" .env 2>/dev/null; then
    warn "GEMINI_API_KEY appears to be empty in .env — the backend will start but LLM calls will fail."
    warn "Get a free key at https://aistudio.google.com/app/apikey"
  fi
fi

# -----------------------------------------------------------------------------
# 2. Python virtual environment
# -----------------------------------------------------------------------------

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  log "Creating Python virtual environment in $VENV_DIR …"
  python3 -m venv "$VENV_DIR"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# -----------------------------------------------------------------------------
# 3. Python dependencies
# -----------------------------------------------------------------------------

log "Installing / upgrading Python dependencies …"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Set PYTHONPATH so 'backend' package is importable by Alembic and uvicorn
export PYTHONPATH="$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# 4. Alembic migrations
# -----------------------------------------------------------------------------

log "Running database migrations …"
alembic upgrade head

# -----------------------------------------------------------------------------
# 5. Frontend dependencies
# -----------------------------------------------------------------------------

log "Installing frontend npm dependencies (fast when packages are cached) …"
(cd frontend && npm install)

# -----------------------------------------------------------------------------
# 6. Start backend (background)
# -----------------------------------------------------------------------------

log "Starting FastAPI backend on http://localhost:8000 …"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Give uvicorn a moment to bind before the frontend proxy tries to connect
sleep 1

# -----------------------------------------------------------------------------
# 7. Start frontend (foreground)
# -----------------------------------------------------------------------------

ok "MAE is starting up!"
ok "  Backend : http://localhost:8000"
ok "  Frontend: http://localhost:5173"
ok "  API docs: http://localhost:8000/docs"
echo ""
log "Press Ctrl-C to stop both servers."
echo ""

# Trap Ctrl-C and kill both processes
cleanup() {
  echo ""
  log "Shutting down …"
  kill "$BACKEND_PID" 2>/dev/null || true
  ok "Done. Goodbye!"
}
trap cleanup INT TERM

(cd frontend && npm run dev)

# If the frontend exits on its own, clean up the backend too
kill "$BACKEND_PID" 2>/dev/null || true
