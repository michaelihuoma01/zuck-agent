#!/usr/bin/env bash
# demo.sh — Demonstrates ZURK's core workflow via the REST API.
#
# Prerequisites:
#   - Backend running on localhost:8000 (./scripts/start.sh --dev)
#   - ANTHROPIC_API_KEY configured in .env
#
# Usage:
#   ./scripts/demo.sh [project_path]
#
# If project_path is omitted, uses /tmp/zurk-demo as a throwaway directory.

set -euo pipefail

BASE_URL="${ZURK_BASE_URL:-http://localhost:8000}"
PROJECT_PATH="${1:-/tmp/zurk-demo}"
API_KEY="${API_KEY:-}"

# ── Helpers ────────────────────────────────────────────────────────

red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
cyan()   { printf '\033[0;36m%s\033[0m\n' "$*"; }
bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

api() {
  local method="$1" path="$2"
  shift 2
  local headers=(-H "Content-Type: application/json")
  if [[ -n "$API_KEY" ]]; then
    headers+=(-H "X-API-Key: $API_KEY")
  fi
  curl -s -X "$method" "${headers[@]}" "$@" "${BASE_URL}${path}"
}

jq_or_cat() {
  if command -v jq &>/dev/null; then
    jq .
  else
    cat
  fi
}

# ── Preflight ──────────────────────────────────────────────────────

bold "=== ZURK Demo Script ==="
echo ""

cyan "1. Checking backend health..."
HEALTH=$(api GET /health)
echo "$HEALTH" | jq_or_cat
echo ""

if echo "$HEALTH" | grep -q '"status":"ok"' 2>/dev/null; then
  green "   Backend is healthy!"
else
  red "   Backend is not responding. Start it with: ./scripts/start.sh --dev"
  exit 1
fi

# ── Create demo directory ──────────────────────────────────────────

if [[ ! -d "$PROJECT_PATH" ]]; then
  cyan "2. Creating demo project directory at $PROJECT_PATH..."
  mkdir -p "$PROJECT_PATH"
  echo '# Demo Project' > "$PROJECT_PATH/README.md"
  green "   Created!"
else
  cyan "2. Using existing directory: $PROJECT_PATH"
fi
echo ""

# ── Register project ──────────────────────────────────────────────

cyan "3. Registering project..."
PROJECT=$(api POST /projects -d "{
  \"name\": \"ZURK Demo\",
  \"path\": \"$PROJECT_PATH\",
  \"description\": \"A demo project to showcase ZURK capabilities\"
}")
echo "$PROJECT" | jq_or_cat

PROJECT_ID=$(echo "$PROJECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [[ -z "$PROJECT_ID" ]]; then
  yellow "   Project may already exist. Listing projects to find it..."
  PROJECTS=$(api GET /projects)
  PROJECT_ID=$(echo "$PROJECTS" | python3 -c "
import sys, json
projects = json.load(sys.stdin)['projects']
for p in projects:
    if p['path'].rstrip('/') == '$PROJECT_PATH'.rstrip('/'):
        print(p['id'])
        break
" 2>/dev/null || echo "")
  if [[ -z "$PROJECT_ID" ]]; then
    red "   Could not find or create project."
    exit 1
  fi
  green "   Found existing project: $PROJECT_ID"
else
  green "   Registered! Project ID: $PROJECT_ID"
fi
echo ""

# ── Create session ─────────────────────────────────────────────────

cyan "4. Starting a session with a simple task..."
SESSION=$(api POST /sessions -d "{
  \"project_id\": \"$PROJECT_ID\",
  \"prompt\": \"Create a file called hello.txt that says 'Hello from ZURK!' — nothing else.\"
}")
echo "$SESSION" | jq_or_cat

SESSION_ID=$(echo "$SESSION" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
if [[ -z "$SESSION_ID" ]]; then
  red "   Failed to create session."
  exit 1
fi
green "   Session started! ID: $SESSION_ID"
echo ""

# ── Poll for status ────────────────────────────────────────────────

cyan "5. Polling session status (Ctrl+C to stop)..."
echo "   The session may pause for approval when Claude tries to write the file."
echo ""

for i in $(seq 1 60); do
  DETAIL=$(api GET "/sessions/$SESSION_ID")
  STATUS=$(echo "$DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
  MSG_COUNT=$(echo "$DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message_count', 0))" 2>/dev/null || echo "0")

  case "$STATUS" in
    running)
      yellow "   [$i] Status: RUNNING ($MSG_COUNT messages)..."
      ;;
    waiting_approval)
      yellow "   [$i] Status: WAITING APPROVAL — Claude wants to use a tool!"
      echo ""

      # Show pending approval details
      APPROVAL=$(echo "$DETAIL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
a = d.get('pending_approval')
if a:
    print(f\"   Tool: {a.get('tool_name', '?')}\")
    print(f\"   Risk: {a.get('risk_level', '?')}\")
" 2>/dev/null || echo "   (approval details unavailable)")
      echo "$APPROVAL"
      echo ""

      cyan "6. Auto-approving the tool use..."
      APPROVE_RESULT=$(api POST "/sessions/$SESSION_ID/approve" -d '{"approved": true}')
      echo "$APPROVE_RESULT" | jq_or_cat
      green "   Approved!"
      echo ""
      ;;
    completed)
      green "   [$i] Status: COMPLETED ($MSG_COUNT messages)"
      echo ""
      break
      ;;
    error)
      ERROR_MSG=$(echo "$DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_message', 'unknown'))" 2>/dev/null || echo "unknown")
      red "   [$i] Status: ERROR — $ERROR_MSG"
      echo ""
      break
      ;;
    idle)
      cyan "   [$i] Status: IDLE ($MSG_COUNT messages)"
      ;;
    *)
      echo "   [$i] Status: $STATUS"
      ;;
  esac

  sleep 2
done

# ── Show results ───────────────────────────────────────────────────

cyan "7. Final session details:"
FINAL=$(api GET "/sessions/$SESSION_ID")
echo "$FINAL" | jq_or_cat
echo ""

# Check if the file was created
if [[ -f "$PROJECT_PATH/hello.txt" ]]; then
  green "8. File created successfully!"
  echo "   Contents of $PROJECT_PATH/hello.txt:"
  echo "   $(cat "$PROJECT_PATH/hello.txt")"
else
  yellow "8. File not found at $PROJECT_PATH/hello.txt (session may still be processing)"
fi

echo ""
bold "=== Demo Complete ==="
echo ""
echo "Next steps:"
echo "  - Open the UI at http://localhost:5173"
echo "  - Navigate to the session to see the full conversation"
echo "  - Try the approval flow from your phone!"
