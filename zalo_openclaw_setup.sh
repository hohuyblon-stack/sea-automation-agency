#!/usr/bin/env bash
# zalo_openclaw_setup.sh — Start OpenClaw gateway + authenticate Zalo Personal
# Run once per session (or install as LaunchAgent for auto-start).

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }
info() { echo -e "${CYAN}---${NC} $1"; }

echo "================================================"
echo "  Zalo + OpenClaw Setup"
echo "================================================"
echo ""

# ── 1. Check openclaw installed ─────────────────────────────────────────────
if ! command -v openclaw &>/dev/null; then
    err "openclaw not found. Install: npm install -g openclaw@latest"
    exit 1
fi
ok "OpenClaw $(openclaw --version) found"

# ── 2. Check zalouser plugin ────────────────────────────────────────────────
if ! openclaw status 2>/dev/null | grep -q "Zalo Personal"; then
    warn "Zalo Personal plugin not detected. Installing..."
    openclaw plugin install @openclaw/zalouser
fi
ok "Zalo Personal plugin enabled"

# ── 3. Start gateway ────────────────────────────────────────────────────────
echo ""
info "Starting OpenClaw gateway..."

# Check if gateway is already running
if curl -sf http://127.0.0.1:18789/health &>/dev/null; then
    ok "Gateway already running on port 18789"
else
    # Start gateway in background
    openclaw gateway &>/dev/null &
    GATEWAY_PID=$!
    echo "$GATEWAY_PID" > /tmp/openclaw_gateway.pid

    # Wait for gateway to be ready (max 15 seconds)
    for i in $(seq 1 15); do
        if curl -sf http://127.0.0.1:18789/health &>/dev/null; then
            ok "Gateway started (PID: $GATEWAY_PID)"
            break
        fi
        if [ "$i" -eq 15 ]; then
            err "Gateway failed to start after 15s"
            err "Try manually: openclaw gateway --verbose"
            exit 1
        fi
        sleep 1
    done
fi

# ── 4. Check Zalo auth status ───────────────────────────────────────────────
echo ""
ZALO_STATE=$(openclaw channels status 2>/dev/null | grep -i "zalo" || true)

if echo "$ZALO_STATE" | grep -qi "authenticated\|ready\|online\|connected"; then
    ok "Zalo already authenticated"
else
    warn "Zalo not authenticated — QR scan required"
    echo ""
    info "A QR code will appear below. Open Zalo on your phone:"
    info "  Settings (gear icon) > QR Scanner > Scan the code"
    echo ""
    read -rp "Press Enter to show QR code..."
    echo ""
    openclaw channels login --channel zalouser
fi

# ── 5. Verify by checking status ────────────────────────────────────────────
echo ""
info "Verifying connection..."
sleep 2

FINAL_STATE=$(openclaw channels status 2>/dev/null | grep -i "zalo" || true)
if echo "$FINAL_STATE" | grep -qi "authenticated\|ready\|online\|connected"; then
    ok "Zalo Personal connected and ready!"
else
    warn "Could not confirm Zalo status. Current state:"
    echo "  $FINAL_STATE"
    echo ""
    warn "If login succeeded, the session is saved — try: openclaw channels status"
fi

# ── 6. Optional: send test message ──────────────────────────────────────────
echo ""
read -rp "Send a test message to yourself? [y/N]: " test_msg
if [[ "$test_msg" =~ ^[Yy]$ ]]; then
    read -rp "Your Zalo phone number (e.g. 0943040916): " test_phone
    openclaw message send \
        --channel zalouser \
        --target "$test_phone" \
        --message "Test tu SEA Automation Agency - OpenClaw + Zalo da ket noi thanh cong!"
    if [ $? -eq 0 ]; then
        ok "Test message sent! Check your Zalo."
    else
        err "Test failed. Check: openclaw logs --follow"
    fi
fi

echo ""
echo "================================================"
echo "  Done. Zalo outreach ready."
echo ""
echo "  Send a message:"
echo "    openclaw message send --channel zalouser -t 09xxx -m 'Hello'"
echo ""
echo "  Run outreach sequence:"
echo "    python outreach/zalo_sequence.py --input leads/data/qualified_2026-03-04.csv --dry-run"
echo "================================================"
