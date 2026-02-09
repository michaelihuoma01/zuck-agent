#!/bin/bash
# Tailscale setup helper for ZURK Agent Command Center
#
# This script helps configure Tailscale for remote access to ZURK,
# including HTTPS via `tailscale serve` and PWA installation from a phone.

set -e

echo "Tailscale Setup for ZURK Agent Command Center"
echo "=============================================="
echo ""

# --- Check Tailscale installation ---
if ! command -v tailscale &>/dev/null; then
  echo "Tailscale is not installed."
  echo ""
  echo "Install instructions:"
  echo "  macOS:  brew install tailscale"
  echo "  Linux:  curl -fsSL https://tailscale.com/install.sh | sh"
  echo ""
  echo "After installing, run: tailscale up"
  exit 1
fi

# --- Check Tailscale is connected ---
STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('BackendState',''))" 2>/dev/null || echo "")
if [ "$STATUS" != "Running" ]; then
  echo "Tailscale is installed but not connected."
  echo "Run: tailscale up"
  exit 1
fi

TS_IP=$(tailscale ip -4 2>/dev/null)
TS_HOSTNAME=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin)['Self']; print(d.get('DNSName','').rstrip('.'))" 2>/dev/null || echo "")

echo "Status:    Connected"
echo "Tailscale IP: ${TS_IP}"
[ -n "$TS_HOSTNAME" ] && echo "Hostname:  ${TS_HOSTNAME}"
echo ""

# --- Setup options ---
echo "Choose setup mode:"
echo ""
echo "  1) Quick — Access via http://${TS_IP}:8000"
echo "     Just start ZURK and access from any device on your tailnet."
echo ""
echo "  2) HTTPS — Access via https://${TS_HOSTNAME} (recommended for PWA)"
echo "     Uses 'tailscale serve' to add TLS. Required for PWA install"
echo "     prompt on some browsers."
echo ""
echo "  3) Funnel — Share outside your tailnet (public internet)"
echo "     Uses 'tailscale funnel' to expose ZURK publicly with HTTPS."
echo "     Use with caution — anyone with the URL can access ZURK."
echo ""
read -p "Select [1/2/3]: " CHOICE

case "$CHOICE" in
  1)
    echo ""
    echo "Quick setup — no extra configuration needed."
    echo ""
    echo "Steps:"
    echo "  1. Start ZURK:    ./scripts/start.sh"
    echo "  2. From your phone or other device, open:"
    echo "     http://${TS_IP}:8000"
    echo ""
    echo "Note: PWA install prompt requires HTTPS. Use option 2 for that."
    ;;
  2)
    echo ""
    echo "Setting up tailscale serve..."
    echo ""
    echo "This will proxy https://${TS_HOSTNAME} → http://localhost:8000"
    echo ""
    read -p "Proceed? [y/N]: " CONFIRM
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
      tailscale serve --bg --https=443 http://localhost:8000
      echo ""
      echo "Done! HTTPS proxy is running in the background."
      echo ""
      echo "Steps:"
      echo "  1. Start ZURK:    ./scripts/start.sh"
      echo "  2. From your phone, open:"
      echo "     https://${TS_HOSTNAME}"
      echo ""
      echo "  To install as PWA on your phone:"
      echo "     iOS:     Open in Safari → Share → Add to Home Screen"
      echo "     Android: Open in Chrome → Menu (⋮) → Install app"
      echo ""
      echo "  To stop the proxy:"
      echo "     tailscale serve --https=443 off"
    fi
    ;;
  3)
    echo ""
    echo "WARNING: Funnel exposes ZURK to the public internet."
    echo "Anyone with the URL can access your Claude Code sessions."
    echo ""
    read -p "Are you sure? [y/N]: " CONFIRM
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
      tailscale funnel --bg --https=443 http://localhost:8000
      echo ""
      echo "Funnel is running. ZURK is accessible at:"
      echo "  https://${TS_HOSTNAME}"
      echo ""
      echo "  To stop: tailscale funnel --https=443 off"
    fi
    ;;
  *)
    echo "Invalid choice."
    exit 1
    ;;
esac
