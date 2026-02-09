#!/bin/bash
# Build a ZURK release tarball with pre-built frontend
#
# Usage:
#   ./scripts/release.sh           # Build zurk-v0.1.0.tar.gz
#   ./scripts/release.sh v0.2.0    # Build zurk-v0.2.0.tar.gz
#
# The tarball includes:
#   - All source code (src/, scripts/, frontend/)
#   - Pre-built frontend (frontend/dist/) so users don't need Node.js
#   - pyproject.toml, .env.example, README.md
#
# After building, create a GitHub Release and upload the tarball:
#   gh release create v0.1.0 dist/zurk-v0.1.0.tar.gz --title "ZURK v0.1.0" --notes "Initial release"

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Version from arg or pyproject.toml
VERSION="${1:-v$(python3 -c "
import re
with open('pyproject.toml') as f:
    m = re.search(r'version\s*=\s*\"(.+?)\"', f.read())
    print(m.group(1) if m else '0.0.0')
")}"

TARBALL_NAME="zurk-${VERSION}.tar.gz"
DIST_DIR="$PROJECT_DIR/dist"
STAGING_DIR=$(mktemp -d)
STAGE="$STAGING_DIR/zurk"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${GREEN}[release]${NC} $1"; }

info "Building ZURK $VERSION"

# --- Build frontend ---

info "Building frontend..."
cd "$PROJECT_DIR/frontend"
npm install --silent 2>/dev/null
npm run build --silent 2>/dev/null || npm run build
cd "$PROJECT_DIR"
info "Frontend built."

# --- Stage files ---

info "Staging release..."
mkdir -p "$STAGE"

# Core source
cp -r src "$STAGE/"
cp -r scripts "$STAGE/"
cp -r frontend "$STAGE/"
cp pyproject.toml "$STAGE/"
cp .env.example "$STAGE/" 2>/dev/null || true
cp README.md "$STAGE/" 2>/dev/null || true
cp CLAUDE.md "$STAGE/" 2>/dev/null || true

# Remove dev artifacts from staging
rm -rf "$STAGE/frontend/node_modules"
rm -rf "$STAGE/frontend/.vite"
rm -rf "$STAGE/scripts/__pycache__"
find "$STAGE/src" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Mark as release (so install.sh knows frontend is pre-built)
echo "$VERSION" > "$STAGE/.zurk-version"

# --- Create tarball ---

mkdir -p "$DIST_DIR"
tar -czf "$DIST_DIR/$TARBALL_NAME" -C "$STAGING_DIR" zurk

# Cleanup
rm -rf "$STAGING_DIR"

SIZE=$(ls -lh "$DIST_DIR/$TARBALL_NAME" | awk '{print $5}')
info "Created: dist/$TARBALL_NAME ($SIZE)"
echo ""
echo -e "${CYAN}To publish:${NC}"
echo "  gh release create $VERSION dist/$TARBALL_NAME \\"
echo "    --title \"ZURK $VERSION\" \\"
echo "    --notes \"Release notes here\""
