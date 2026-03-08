#!/usr/bin/env bash
# setup_vela_domain.sh — Switch SEA Automation Agency to Vela brand + professional email
# Run AFTER you have: (1) bought vela.vn, (2) set up Zoho Mail, (3) verified DNS
#
# Usage:
#   bash ~/sea-automation-agency/scripts/setup_vela_domain.sh
#   bash ~/sea-automation-agency/scripts/setup_vela_domain.sh --update-only   # skip domain checks

set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
step() { echo -e "\n${GREEN}▶ $1${NC}"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

UPDATE_ONLY=false
[[ "${1:-}" == "--update-only" ]] && UPDATE_ONLY=true

# ---------------------------------------------------------------------------
# STEP 1 — Check domain availability
# ---------------------------------------------------------------------------
if [[ "$UPDATE_ONLY" == "false" ]]; then
  step "Checking domain availability"

  for domain in "vela.vn" "vela.agency" "getvela.com"; do
    result=$(whois "$domain" 2>/dev/null | grep -iE "No match|NOT FOUND|Status: free|available" | head -1 || true)
    if [[ -n "$result" ]]; then
      ok "$domain appears AVAILABLE"
    else
      registered=$(whois "$domain" 2>/dev/null | grep -iE "Registrar:|Expiry|Creation" | head -1 || true)
      if [[ -n "$registered" ]]; then
        warn "$domain is taken — $registered"
      else
        warn "$domain — could not determine (check manually)"
      fi
    fi
  done

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  MANUAL STEPS — complete these before re-running this script"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "  1. BUY THE DOMAIN"
  echo "     → https://www.namecheap.com  (search: vela.vn)"
  echo "     → OR https://inet.vn         (for .vn — often cheaper in Vietnam)"
  echo "     → Cost: ~150,000 VND/year for .vn"
  echo ""
  echo "  2. SET UP FREE BUSINESS EMAIL (Zoho Mail)"
  echo "     → https://www.zoho.com/mail/zohomail-pricing.html"
  echo "     → Choose 'Forever Free' plan"
  echo "     → Add your domain: vela.vn"
  echo "     → Create: huy@vela.vn"
  echo ""
  echo "  3. ADD DNS RECORDS (in your domain registrar)"
  echo "     Zoho will give you MX records to add — takes 5 min"
  echo "     Wait 10-30 min for DNS to propagate"
  echo ""
  echo "  4. TEST the email works (send test from Zoho webmail)"
  echo ""
  echo "  Then run:"
  echo "     bash ~/sea-automation-agency/scripts/setup_vela_domain.sh --update-only"
  echo ""
  exit 0
fi

# ---------------------------------------------------------------------------
# STEP 2 — Collect new email
# ---------------------------------------------------------------------------
step "Configure new Vela email"

read -rp "Enter your new professional email (e.g. huy@vela.vn): " NEW_EMAIL
[[ -z "$NEW_EMAIL" ]] && fail "Email cannot be empty"
[[ "$NEW_EMAIL" != *"@"* ]] && fail "Not a valid email address"

read -rp "Enter your display name (e.g. Huy — Vela): " NEW_NAME
[[ -z "$NEW_NAME" ]] && NEW_NAME="Huy — Vela"

# ---------------------------------------------------------------------------
# STEP 3 — Update .env
# ---------------------------------------------------------------------------
step "Updating .env"

# Backup first
cp .env .env.backup
ok "Backed up .env → .env.backup"

sed -i '' "s|^SENDER_EMAIL=.*|SENDER_EMAIL=${NEW_EMAIL}|" .env
sed -i '' "s|^SENDER_NAME=.*|SENDER_NAME=${NEW_NAME}|" .env
ok "Updated SENDER_EMAIL → ${NEW_EMAIL}"
ok "Updated SENDER_NAME  → ${NEW_NAME}"

# ---------------------------------------------------------------------------
# STEP 4 — Update email templates (replace old gmail in signatures)
# ---------------------------------------------------------------------------
step "Updating email templates"

OLD_EMAIL=$(grep "^SENDER_EMAIL=" .env.backup | cut -d= -f2)
TEMPLATE_DIR="outreach/templates"
UPDATED=0

for f in "$TEMPLATE_DIR"/*.md; do
  if grep -q "$OLD_EMAIL" "$f" 2>/dev/null; then
    sed -i '' "s|${OLD_EMAIL}|${NEW_EMAIL}|g" "$f"
    ok "Updated: $f"
    ((UPDATED++)) || true
  fi
done

if [[ $UPDATED -eq 0 ]]; then
  warn "No templates contained old email — nothing replaced (fine if templates use {sender_email} variable)"
fi

# ---------------------------------------------------------------------------
# STEP 5 — Delete old token so re-auth uses new email
# ---------------------------------------------------------------------------
step "Clearing old Google OAuth token"

if [[ -f "token.json" ]]; then
  mv token.json token.json.old_gmail_backup
  ok "Moved token.json → token.json.old_gmail_backup"
else
  warn "token.json not found — skipping"
fi

# ---------------------------------------------------------------------------
# STEP 6 — Re-auth Google OAuth
# ---------------------------------------------------------------------------
step "Re-authenticating Google OAuth with new email"
echo ""
warn "A browser window will open. Sign in with the Google account"
warn "that controls ${NEW_EMAIL} (or your Google Workspace account for vela.vn)"
echo ""
read -rp "Press Enter when ready to open browser..."

bash scripts/reauth_all_scopes.sh

# ---------------------------------------------------------------------------
# STEP 7 — Verify
# ---------------------------------------------------------------------------
step "Verifying setup"

source venv/bin/activate 2>/dev/null || true

python3 -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()
email = os.getenv('SENDER_EMAIL', '')
name  = os.getenv('SENDER_NAME', '')
print(f'  SENDER_EMAIL = {email}')
print(f'  SENDER_NAME  = {name}')
if '@gmail.com' in email:
    print('  WARNING: still using Gmail address')
    sys.exit(1)
else:
    print('  Looks good — professional email set')
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Vela email setup complete!"
echo ""
echo "  Sending email  : $(grep '^SENDER_EMAIL=' .env | cut -d= -f2)"
echo "  Display name   : $(grep '^SENDER_NAME=' .env | cut -d= -f2)"
echo ""
echo "  Next: run a dry-run to confirm templates look right"
echo "  → /send-outreach --day 1 --dry-run"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
