#!/usr/bin/env bash
# setup.sh — SEA Automation Agency one-time setup
# Run this instead of asking Claude to do it.

set -e
cd "$(dirname "$0")"

ENV_FILE=".env"
TOKEN_FILE="token.json"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

echo "================================================"
echo "  SEA Agency Setup"
echo "================================================"

# ── 1. Apify token ────────────────────────────────────
if grep -q "^APIFY_API_TOKEN=" "$ENV_FILE" 2>/dev/null; then
  ok "APIFY_API_TOKEN already set"
else
  warn "APIFY_API_TOKEN missing."
  echo "  Get it at: https://console.apify.com/account/integrations"
  read -rp "  Paste token (or Enter to skip): " apify_token
  if [[ -n "$apify_token" ]]; then
    echo "" >> "$ENV_FILE"
    echo "# Apify (Shopee scraper)" >> "$ENV_FILE"
    echo "APIFY_API_TOKEN=$apify_token" >> "$ENV_FILE"
    ok "APIFY_API_TOKEN saved"
  else
    warn "Skipped — Shopee lead scraping won't work"
  fi
fi

# ── 2. Hunter.io key ──────────────────────────────────
if grep -q "^HUNTER_API_KEY=" "$ENV_FILE" 2>/dev/null; then
  ok "HUNTER_API_KEY already set"
else
  warn "HUNTER_API_KEY missing."
  echo "  Get it at: https://hunter.io/api_keys"
  read -rp "  Paste key (or Enter to skip): " hunter_key
  if [[ -n "$hunter_key" ]]; then
    echo "" >> "$ENV_FILE"
    echo "# Hunter.io (email enrichment)" >> "$ENV_FILE"
    echo "HUNTER_API_KEY=$hunter_key" >> "$ENV_FILE"
    ok "HUNTER_API_KEY saved"
  else
    warn "Skipped — email enrichment won't work"
  fi
fi

# ── 3. Google OAuth re-auth ───────────────────────────
if [[ -f "$TOKEN_FILE" ]]; then
  warn "Deleting old token.json to force re-auth with Sheets scope..."
  rm "$TOKEN_FILE"
  ok "token.json deleted"
  echo ""
  echo "  Now triggering re-auth. A browser window will open."
  echo "  Make sure to click ALLOW — the new auth includes Sheets access."
  echo ""
  source venv/bin/activate 2>/dev/null || true
  python outreach/send_sequence.py --dry-run 2>/dev/null || \
    python -c "
from outreach.send_sequence import get_gmail_service
get_gmail_service()
print('Auth complete.')
" || warn "Could not auto-trigger auth — run any script manually to complete it."
else
  ok "No stale token.json found"
fi

# ── 4. Start reply monitor ────────────────────────────
echo ""
read -rp "Start reply monitor in background? [y/N]: " start_monitor
if [[ "$start_monitor" =~ ^[Yy]$ ]]; then
  source venv/bin/activate 2>/dev/null || true
  nohup python outreach/reply_monitor.py > logs/reply_monitor.log 2>&1 &
  echo $! > .reply_monitor.pid
  ok "Reply monitor started (PID: $!). Logs: logs/reply_monitor.log"
fi

echo ""
echo "================================================"
echo "  Done. Next steps:"
echo "  - March 10: run /followup for Day 4 emails"
echo "  - March 16: run /followup for Day 10 break-up"
echo "================================================"
