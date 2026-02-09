#!/bin/bash
# ZURK Health Monitor
#
# Pings /health endpoint. If unhealthy, restarts the launchd service.
# Designed to run via launchd every 5 minutes (see com.zurk.healthcheck.plist).
#
# Can also be run manually:
#   ./scripts/healthcheck.sh         # Single check
#   ./scripts/healthcheck.sh --loop  # Continuous (5-min interval)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/healthcheck.log"
HEALTH_URL="http://localhost:8000/health"
PLIST_NAME="com.zurk.agent-center"
MAX_RETRIES=3
RETRY_DELAY=5

mkdir -p "$PROJECT_DIR/logs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

check_health() {
    local response
    response=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null)
    [ "$response" = "200" ]
}

restart_service() {
    log "[RESTART] Attempting service restart..."
    local uid
    uid=$(id -u)

    # Try modern launchctl commands first, fall back to legacy
    launchctl kickstart -k "gui/$uid/$PLIST_NAME" 2>/dev/null || {
        launchctl bootout "gui/$uid/$PLIST_NAME" 2>/dev/null
        sleep 2
        launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/${PLIST_NAME}.plist" 2>/dev/null
    }

    # Wait for startup
    sleep 5

    if check_health; then
        log "[RESTART] Service recovered successfully."
    else
        log "[RESTART] Service still unhealthy after restart!"
    fi
}

do_check() {
    for attempt in $(seq 1 $MAX_RETRIES); do
        if check_health; then
            # Only log every 12th check (~hourly) to avoid log noise
            local hour_min
            hour_min=$(date '+%M')
            if [ "$hour_min" -lt 5 ]; then
                log "[OK] Health check passed."
            fi
            return 0
        fi
        if [ "$attempt" -lt "$MAX_RETRIES" ]; then
            sleep "$RETRY_DELAY"
        fi
    done

    log "[FAIL] Health check failed after $MAX_RETRIES attempts."
    restart_service
    return 1
}

# --- Main ---

if [ "$1" = "--loop" ]; then
    log "[START] Health monitor started (loop mode, 300s interval)."
    while true; do
        do_check
        sleep 300
    done
else
    do_check
fi
