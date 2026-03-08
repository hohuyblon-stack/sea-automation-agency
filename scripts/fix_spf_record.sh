#!/usr/bin/env bash
# fix_spf_record.sh — Update wove.agency SPF record to authorize Gmail sending
#
# Problem: Gmail "Send As" huy@wove.agency gets rejected (550 auth required)
#          because SPF only includes ImprovMX, not Google.
#
# Fix: Update TXT record to include both.
#
# Before: v=spf1 include:spf.improvmx.com ~all
# After:  v=spf1 include:_spf.google.com include:spf.improvmx.com ~all
#
# This script opens Namecheap DNS management in your browser, then verifies.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }

echo "========================================"
echo "  Fix SPF Record for wove.agency"
echo "========================================"
echo ""

# ── 1. Show current state ────────────────────────────────────────────────────
info "Current SPF record:"
CURRENT_SPF=$(dig TXT wove.agency +short 2>/dev/null | grep spf || echo "(none found)")
echo "  $CURRENT_SPF"
echo ""

if echo "$CURRENT_SPF" | grep -q "_spf.google.com"; then
    ok "SPF already includes Google — no change needed!"
    echo ""
    info "Verifying with a test email..."
    cd ~/sea-automation-agency
    source venv/bin/activate 2>/dev/null || true
    python outreach/send_sequence.py --to "hohuyblon@gmail.com" --name "SPF Test" --business "Test" --lang vi 2>&1 | grep -E "Sent|Error|error|fail"
    exit 0
fi

# ── 2. Open Namecheap DNS ────────────────────────────────────────────────────
warn "SPF does NOT include Google. Opening Namecheap DNS management..."
echo ""
info "Steps in the browser:"
echo "  1. Find the TXT record with value: v=spf1 include:spf.improvmx.com ~all"
echo "  2. Edit it to:"
echo ""
echo "     v=spf1 include:_spf.google.com include:spf.improvmx.com ~all"
echo ""
echo "  3. Click the green checkmark to save"
echo "  4. Click 'Save All Changes' at the bottom"
echo ""

open "https://ap.www.namecheap.com/domains/domaincontrolpanel/wove.agency/advancedns"

# ── 3. Wait for user to make the change ──────────────────────────────────────
echo ""
read -rp "Press Enter after you've saved the DNS change..."

# ── 4. Poll for propagation (max 5 min) ─────────────────────────────────────
echo ""
info "Checking DNS propagation (may take 1-5 minutes)..."

for i in $(seq 1 30); do
    NEW_SPF=$(dig TXT wove.agency +short @8.8.8.8 2>/dev/null | grep spf || echo "")
    if echo "$NEW_SPF" | grep -q "_spf.google.com"; then
        ok "SPF updated and propagated!"
        echo "  $NEW_SPF"
        break
    fi
    if [ "$i" -eq 30 ]; then
        warn "DNS hasn't propagated yet (can take up to 30 min)."
        warn "Current: $NEW_SPF"
        echo ""
        echo "  You can re-run this script later to verify."
        exit 0
    fi
    printf "  Waiting... (%d/30)\r" "$i"
    sleep 10
done

# ── 5. Send test email ──────────────────────────────────────────────────────
echo ""
info "Sending test email to hohuyblon@gmail.com..."
cd ~/sea-automation-agency
source venv/bin/activate 2>/dev/null || true
python outreach/send_sequence.py --to "hohuyblon@gmail.com" --name "SPF Verified" --business "Wove Test" --lang vi 2>&1 | grep -E "Sent|Error|error|fail"

echo ""
ok "Done! Check your Gmail inbox for the test email."
echo ""
echo "  If it arrives (not in spam) → SPF is working."
echo "  Then run the real outreach:"
echo "    python outreach/send_sequence.py --input leads/data/qualified_2026-03-04.csv --lang vi --delay 30"
echo "========================================"
