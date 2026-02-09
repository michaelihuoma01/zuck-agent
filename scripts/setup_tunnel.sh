#!/bin/bash
# Cloudflare Tunnel setup helper for ZURK

set -e

echo "Cloudflare Tunnel Setup for ZURK Agent Command Center"
echo "======================================================"
echo ""

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "cloudflared is not installed."
    echo ""
    echo "Install instructions:"
    echo "  macOS: brew install cloudflared"
    echo "  Linux: See https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
    echo ""
    exit 1
fi

echo "To create a Cloudflare Tunnel for ZURK:"
echo ""
echo "1. Authenticate with Cloudflare:"
echo "   cloudflared tunnel login"
echo ""
echo "2. Create a tunnel:"
echo "   cloudflared tunnel create zurk"
echo ""
echo "3. Route traffic to your tunnel:"
echo "   cloudflared tunnel route dns zurk zurk.yourdomain.com"
echo ""
echo "4. Start the tunnel:"
echo "   cloudflared tunnel run --url http://localhost:8000 zurk"
echo ""
echo "For more info: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/"
