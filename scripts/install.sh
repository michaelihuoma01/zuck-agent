#!/bin/bash
# ZURK Agent Command Center — Quick Installer
#
# Install from anywhere (no git required):
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/zurk/main/scripts/install.sh | bash
#
# Or clone and run locally:
#   git clone https://github.com/YOUR_USER/zurk.git && cd zurk && ./scripts/install.sh
#
# Environment variables:
#   ZURK_INSTALL_DIR  — install location (default: ~/zurk)
#   ANTHROPIC_API_KEY — skip interactive prompt
#
# What this does:
#   1. Downloads latest release tarball (or uses local repo)
#   2. Checks prerequisites (Python 3.11+)
#   3. Creates venv and installs Python dependencies
#   4. Uses pre-built frontend from tarball (no Node.js needed for release installs)
#   5. Prompts for ANTHROPIC_API_KEY and creates .env
#   6. Optionally installs as a macOS launchd service (auto-start on boot)

set -e

GITHUB_REPO="YOUR_USER/zurk"

# --- Colors & helpers ---

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[zurk]${NC} $1"; }
warn()  { echo -e "${YELLOW}[zurk]${NC} $1"; }
error() { echo -e "${RED}[zurk]${NC} $1" >&2; }
header() { echo -e "\n${CYAN}${BOLD}$1${NC}\n"; }

# --- Banner ---

echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   ZURK — Agent Command Center         ║"
echo "  ║   Remote control for Claude sessions   ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

# --- Determine install mode ---

SCRIPT_DIR=""
PROJECT_DIR=""
FROM_RELEASE=false

if [ -f "pyproject.toml" ] && grep -q "zurk" pyproject.toml 2>/dev/null; then
    # Running from inside the repo (git clone or extracted tarball)
    PROJECT_DIR="$(pwd)"
    SCRIPT_DIR="$PROJECT_DIR/scripts"
    [ -f ".zurk-version" ] && FROM_RELEASE=true
elif [ -f "$(dirname "$0")/install_service.sh" ] 2>/dev/null; then
    # Running from scripts/ directory
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    [ -f "$PROJECT_DIR/.zurk-version" ] && FROM_RELEASE=true
else
    # Running from curl pipe — download latest release
    FROM_RELEASE=true
    INSTALL_DIR="${ZURK_INSTALL_DIR:-$HOME/zurk}"

    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/pyproject.toml" ]; then
        warn "Existing ZURK installation found at $INSTALL_DIR"
        read -rp "Update it? [Y/n] " answer </dev/tty
        if [ "${answer,,}" = "n" ]; then
            exit 0
        fi
        # Preserve .env across update
        [ -f "$INSTALL_DIR/.env" ] && cp "$INSTALL_DIR/.env" /tmp/.zurk-env-backup
    fi

    header "Downloading latest ZURK release..."

    # Try GitHub Releases API for latest tarball
    RELEASE_URL=""
    if command -v curl &>/dev/null; then
        RELEASE_JSON=$(curl -sf "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" 2>/dev/null || echo "")
        if [ -n "$RELEASE_JSON" ]; then
            RELEASE_URL=$(echo "$RELEASE_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for asset in data.get('assets', []):
        if asset['name'].endswith('.tar.gz'):
            print(asset['browser_download_url'])
            break
except: pass
" 2>/dev/null)
        fi
    fi

    if [ -n "$RELEASE_URL" ]; then
        info "Found release: $RELEASE_URL"
        TMPFILE=$(mktemp)
        curl -fSL "$RELEASE_URL" -o "$TMPFILE"
        mkdir -p "$(dirname "$INSTALL_DIR")"
        # Extract tarball (contains zurk/ directory)
        tar -xzf "$TMPFILE" -C "$(dirname "$INSTALL_DIR")"
        # The tarball extracts to a "zurk" directory
        if [ -d "$(dirname "$INSTALL_DIR")/zurk" ] && [ "$(dirname "$INSTALL_DIR")/zurk" != "$INSTALL_DIR" ]; then
            mv "$(dirname "$INSTALL_DIR")/zurk" "$INSTALL_DIR"
        fi
        rm -f "$TMPFILE"
        info "Extracted to $INSTALL_DIR"
    else
        # Fallback: clone from git
        warn "No release found. Falling back to git clone..."
        if ! command -v git &>/dev/null; then
            error "Neither a GitHub Release nor git is available."
            error "Install git or create a GitHub Release first."
            exit 1
        fi
        git clone "https://github.com/${GITHUB_REPO}.git" "$INSTALL_DIR"
    fi

    # Restore .env if backed up
    [ -f /tmp/.zurk-env-backup ] && mv /tmp/.zurk-env-backup "$INSTALL_DIR/.env"

    PROJECT_DIR="$INSTALL_DIR"
    SCRIPT_DIR="$PROJECT_DIR/scripts"
    cd "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# --- Check prerequisites ---

header "Checking prerequisites..."

MISSING=0

# Python 3.11+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
        info "Python $PY_VERSION"
    else
        error "Python 3.11+ required (found $PY_VERSION)"
        MISSING=1
    fi
else
    error "Python 3 not found. Install from https://python.org"
    MISSING=1
fi

# Node.js — only required if frontend isn't pre-built
if [ "$FROM_RELEASE" = true ] && [ -d "frontend/dist" ]; then
    info "Frontend pre-built (release install — Node.js not required)"
else
    if command -v node &>/dev/null; then
        NODE_VERSION=$(node --version | tr -d 'v' | cut -d. -f1)
        if [ "$NODE_VERSION" -ge 18 ]; then
            info "Node.js $(node --version)"
        else
            error "Node.js 18+ required (found v$NODE_VERSION)"
            MISSING=1
        fi
    else
        error "Node.js not found (needed to build frontend). Install from https://nodejs.org"
        MISSING=1
    fi

    if ! command -v npm &>/dev/null; then
        error "npm not found."
        MISSING=1
    else
        info "npm $(npm --version)"
    fi
fi

# Claude Code CLI (optional)
if command -v claude &>/dev/null; then
    info "Claude Code CLI: $(claude --version 2>&1 | head -1)"
else
    warn "Claude Code CLI not found (optional). Install: npm install -g @anthropic-ai/claude-code"
fi

if [ "$MISSING" -gt 0 ]; then
    error "Missing prerequisites. Install them and re-run this script."
    exit 1
fi

info "All prerequisites met!"

# --- Python virtual environment ---

header "Setting up Python environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    info "Virtual environment created."
else
    info "Virtual environment already exists."
fi

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"
info "Python dependencies installed."

# --- Frontend ---

header "Setting up frontend..."

if [ -d "frontend/dist" ]; then
    info "Frontend already built ($(ls frontend/dist/assets/*.js 2>/dev/null | wc -l | tr -d ' ') assets)."
else
    cd frontend
    if [ ! -d "node_modules" ]; then
        npm install --silent
        info "Frontend dependencies installed."
    fi
    npm run build --silent 2>/dev/null || npm run build
    info "Frontend built."
    cd "$PROJECT_DIR"
fi

# --- Environment file ---

header "Configuring environment..."

if [ ! -f ".env" ]; then
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" > .env
        info "API key set from environment."
    else
        echo ""
        echo "  ZURK needs your Anthropic API key to run Claude sessions."
        echo "  Get one at: https://console.anthropic.com/settings/keys"
        echo ""
        read -rsp "  Enter your ANTHROPIC_API_KEY (hidden): " api_key </dev/tty
        echo ""
        if [ -n "$api_key" ]; then
            echo "ANTHROPIC_API_KEY=$api_key" > .env
            info "API key saved to .env"
        else
            warn "No API key provided. Add it later: echo 'ANTHROPIC_API_KEY=sk-...' > $PROJECT_DIR/.env"
            cp .env.example .env 2>/dev/null || touch .env
        fi
    fi
else
    info ".env already exists."
fi

# --- Initialize database ---

header "Initializing database..."

mkdir -p data logs backups
.venv/bin/python -c "
import asyncio
from src.models import init_db
asyncio.run(init_db())
print('Database initialized.')
" 2>/dev/null && info "Database ready." || {
    info "Database will be initialized on first startup."
}

# --- Install service (macOS) ---

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    read -rp "Install as auto-start service (launchd)? [Y/n] " install_service </dev/tty
    if [ "${install_service,,}" != "n" ]; then
        bash "$SCRIPT_DIR/install_service.sh"
    else
        info "Skipping service installation. Start manually with: ./scripts/start.sh"
    fi
fi

# --- Tailscale (optional) ---

if ! command -v tailscale &>/dev/null; then
    echo ""
    warn "Tailscale not installed. For remote access from your phone:"
    warn "  1. Install: https://tailscale.com/download"
    warn "  2. Run: ./scripts/setup_tailscale.sh"
fi

# --- Done ---

header "Installation complete!"

echo -e "  ${BOLD}Quick start:${NC}"
echo "    cd $PROJECT_DIR"
echo "    ./scripts/start.sh          # Production mode"
echo "    ./scripts/start.sh --dev    # Development mode"
echo ""
echo -e "  ${BOLD}Access:${NC}"
echo "    Local:  http://localhost:8000"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")
if [ -n "$LAN_IP" ]; then
    echo "    LAN:    http://${LAN_IP}:8000"
fi

if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
        echo "    Phone:  http://${TS_IP}:8000  (add to home screen as PWA)"
    fi
fi

echo ""
echo -e "  ${BOLD}Remote access setup:${NC}"
echo "    ./scripts/setup_tailscale.sh    # Configure Tailscale HTTPS"
echo ""
echo -e "  ${BOLD}Management:${NC}"
echo "    ./scripts/zurk status           # Check if running"
echo "    ./scripts/zurk logs             # View logs"
echo "    ./scripts/backup_db.sh --list   # View database backups"
echo ""
info "ZURK is ready. Happy building!"
