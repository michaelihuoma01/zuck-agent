#!/bin/bash
# Start ZURK Agent Command Center — backend + frontend
#
# Usage:
#   ./scripts/start.sh          # Production: uvicorn + serve frontend/dist
#   ./scripts/start.sh --dev    # Development: uvicorn --reload + vite dev
#   ./scripts/start.sh --build  # Production: force-rebuild frontend first

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Parse flags
DEV_MODE=false
FORCE_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --dev)  DEV_MODE=true ;;
    --build) FORCE_BUILD=true ;;
  esac
done

# Load environment variables
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

# Track child PIDs for cleanup
PIDS=()

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
  echo "Done."
  exit 0
}

trap cleanup SIGINT SIGTERM

# --- Detect network addresses ---
print_urls() {
  echo ""
  echo "  ZURK Agent Command Center"
  echo "  ========================="
  echo ""
  echo "  Local:      http://localhost:${PORT}"

  # LAN IP (macOS / Linux)
  LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")
  if [ -n "$LAN_IP" ]; then
    echo "  LAN:        http://${LAN_IP}:${PORT}"
  fi

  # Tailscale IP
  if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
      echo "  Tailscale:  http://${TS_IP}:${PORT}"
    fi
  fi

  echo ""
  if [ "$DEV_MODE" = true ]; then
    echo "  Frontend:   http://localhost:${FRONTEND_PORT} (Vite dev)"
  fi
  echo "  Mode:       $([ "$DEV_MODE" = true ] && echo 'Development' || echo 'Production')"
  echo ""
}

# --- Start backend ---
echo "Starting backend..."
if [ "$DEV_MODE" = true ]; then
  uvicorn src.main:app --reload --host "$HOST" --port "$PORT" &
else
  uvicorn src.main:app --host "$HOST" --port "$PORT" &
fi
PIDS+=($!)

# --- Start frontend ---
if [ "$DEV_MODE" = true ]; then
  echo "Starting Vite dev server..."
  cd frontend
  npm run dev &
  PIDS+=($!)
  cd "$PROJECT_DIR"
else
  # Build frontend if dist doesn't exist or --build flag
  if [ ! -d frontend/dist ] || [ "$FORCE_BUILD" = true ]; then
    echo "Building frontend..."
    cd frontend
    npm run build
    cd "$PROJECT_DIR"
  fi
  echo "Serving frontend from frontend/dist..."
  npx serve frontend/dist -l "$FRONTEND_PORT" -s &
  PIDS+=($!)
fi

print_urls

# Wait for any child to exit
wait -n 2>/dev/null || wait
