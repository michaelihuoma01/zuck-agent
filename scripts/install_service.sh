#!/bin/bash
# Install ZURK as a macOS launchd service (auto-start on boot, auto-restart on crash)
#
# Usage:
#   ./scripts/install_service.sh          # Install and start
#   ./scripts/install_service.sh --remove # Uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"
PLIST_NAME="com.zurk.agent-center"
PLIST_SRC="$SCRIPT_DIR/${PLIST_NAME}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

HEALTHCHECK_NAME="com.zurk.healthcheck"
HEALTHCHECK_SRC="$SCRIPT_DIR/${HEALTHCHECK_NAME}.plist"
HEALTHCHECK_DST="$HOME/Library/LaunchAgents/${HEALTHCHECK_NAME}.plist"

BACKUP_NAME="com.zurk.backup"
BACKUP_SRC="$SCRIPT_DIR/${BACKUP_NAME}.plist"
BACKUP_DST="$HOME/Library/LaunchAgents/${BACKUP_NAME}.plist"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[zurk]${NC} $1"; }
warn()  { echo -e "${YELLOW}[zurk]${NC} $1"; }
error() { echo -e "${RED}[zurk]${NC} $1"; }

unload_plist() {
    local name="$1" dst="$2"
    if launchctl list "$name" &>/dev/null; then
        launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || \
        launchctl unload "$dst" 2>/dev/null || true
    fi
    [ -f "$dst" ] && rm "$dst"
}

remove_service() {
    info "Removing all ZURK services..."
    unload_plist "$PLIST_NAME" "$PLIST_DST"
    unload_plist "$HEALTHCHECK_NAME" "$HEALTHCHECK_DST"
    unload_plist "$BACKUP_NAME" "$BACKUP_DST"
    info "Done. All ZURK services uninstalled."
    exit 0
}

if [ "$1" = "--remove" ] || [ "$1" = "--uninstall" ]; then
    remove_service
fi

# --- Preflight checks ---

if [ ! -d "$VENV_DIR" ]; then
    error "Virtual environment not found at $VENV_DIR"
    error "Run: python3 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

if [ ! -f "$VENV_DIR/bin/uvicorn" ]; then
    error "uvicorn not found in venv. Run: .venv/bin/pip install -e ."
    exit 1
fi

# Create required directories
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
mkdir -p "$PROJECT_DIR/data"

# --- Load .env for ANTHROPIC_API_KEY ---

ENV_BLOCK=""
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        # Strip surrounding quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        ENV_BLOCK="$ENV_BLOCK        <key>$key</key>\n        <string>$value</string>\n"
    done < "$PROJECT_DIR/.env"
fi

# --- Generate plist from template ---

info "Generating launchd plist..."

# Replace placeholders
sed \
    -e "s|__PROJECT__|$PROJECT_DIR|g" \
    -e "s|__VENV__|$VENV_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# Inject .env variables into EnvironmentVariables dict
if [ -n "$ENV_BLOCK" ]; then
    # Insert env vars before the closing </dict> of EnvironmentVariables
    # We find the VIRTUAL_ENV line and append after it
    python3 -c "
import re, sys
with open('$PLIST_DST', 'r') as f:
    content = f.read()
# Add env vars after VIRTUAL_ENV string entry
marker = '<string>$VENV_DIR</string>'
idx = content.find(marker)
if idx >= 0:
    insert_at = content.find('\n', idx) + 1
    env_block = '''$ENV_BLOCK'''
    content = content[:insert_at] + env_block + content[insert_at:]
with open('$PLIST_DST', 'w') as f:
    f.write(content)
"
fi

info "Plist installed to $PLIST_DST"

# --- Stop existing service if running ---

if launchctl list "$PLIST_NAME" &>/dev/null; then
    warn "Stopping existing service..."
    launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || \
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    sleep 1
fi

# --- Load and start ---

info "Loading service..."
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || \
launchctl load "$PLIST_DST" 2>/dev/null

sleep 2

# --- Verify ---

if launchctl list "$PLIST_NAME" &>/dev/null; then
    info "Service is running!"
else
    error "Service failed to start. Check logs:"
    error "  tail -f $PROJECT_DIR/logs/zurk-stderr.log"
    exit 1
fi

# Health check
sleep 3
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    info "Health check passed — ZURK is live at http://localhost:8000"
else
    warn "Server started but health check pending (may still be initializing)"
    warn "  Check: curl http://localhost:8000/health"
fi

# --- Install healthcheck (5-minute interval) ---

install_aux_plist() {
    local name="$1" src="$2" dst="$3"
    sed -e "s|__PROJECT__|$PROJECT_DIR|g" "$src" > "$dst"
    # Stop if already running
    launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || \
    launchctl unload "$dst" 2>/dev/null || true
    # Start
    launchctl bootstrap "gui/$(id -u)" "$dst" 2>/dev/null || \
    launchctl load "$dst" 2>/dev/null
    info "Installed $name"
}

install_aux_plist "$HEALTHCHECK_NAME" "$HEALTHCHECK_SRC" "$HEALTHCHECK_DST"
install_aux_plist "$BACKUP_NAME" "$BACKUP_SRC" "$BACKUP_DST"

echo ""
info "ZURK production services installed:"
info "  Server:      auto-start on boot, auto-restart on crash"
info "  Healthcheck: pings /health every 5 minutes, restarts if down"
info "  Backup:      daily at 3 AM, keeps last 7 days"
info ""
info "Commands:"
info "  Stop:    launchctl bootout gui/$(id -u)/$PLIST_NAME"
info "  Start:   launchctl bootstrap gui/$(id -u) $PLIST_DST"
info "  Status:  launchctl list $PLIST_NAME"
info "  Logs:    tail -f $PROJECT_DIR/logs/zurk.log"
info "  Backups: ./scripts/backup_db.sh --list"
info "  Remove:  ./scripts/install_service.sh --remove"
