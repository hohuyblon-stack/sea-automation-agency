#!/bin/bash
# setup.sh — First-run setup for SEA Automation Agency
# Run: bash scripts/setup.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

log "=== SEA Automation Agency — First Run Setup ==="
echo ""

# ---------------------------------------------------------------------------
# 1. Check Python version
# ---------------------------------------------------------------------------
log "Checking Python version..."
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    error "Python 3 is required. Install it from https://python.org"
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    error "Python 3.9+ required. Found: $PYTHON_VERSION"
fi

log "Python OK: $PYTHON_VERSION"

# ---------------------------------------------------------------------------
# 2. Create virtual environment
# ---------------------------------------------------------------------------
if [ ! -d "venv" ]; then
    log "Creating virtual environment..."
    $PYTHON -m venv venv
else
    log "Virtual environment already exists."
fi

# Activate venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    error "Could not activate virtual environment"
fi

log "Virtual environment activated."

# ---------------------------------------------------------------------------
# 3. Install dependencies
# ---------------------------------------------------------------------------
log "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
log "Dependencies installed."

# ---------------------------------------------------------------------------
# 4. Create directory structure
# ---------------------------------------------------------------------------
log "Creating directories..."
mkdir -p leads/data
mkdir -p leads/scrapers
mkdir -p outreach/templates
mkdir -p proposals/templates
mkdir -p proposals/generated
mkdir -p delivery/templates/order_sync/data
mkdir -p delivery/templates/order_sync/logs
mkdir -p delivery/templates/inventory_alerts/data
mkdir -p delivery/templates/inventory_alerts/logs
mkdir -p delivery/templates/reporting_dashboard/reports
mkdir -p clients
mkdir -p reports/output
mkdir -p generated
log "Directories created."

# ---------------------------------------------------------------------------
# 5. .env file
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn ".env created from .env.example — fill in your credentials!"
    else
        warn ".env.example not found — creating minimal .env"
        cat > .env << 'EOF'
SENDER_NAME=
SENDER_EMAIL=
SENDER_ZALO=
SHEETS_CRM_ID=
FACEBOOK_ACCESS_TOKEN=
EOF
    fi
else
    log ".env already exists."
fi

# ---------------------------------------------------------------------------
# 6. Check credentials.json and set up Google auth
# ---------------------------------------------------------------------------
# NOTE: gcloud CLI is NOT required. Authentication is handled directly
# via OAuth2 using credentials.json from Google Cloud Console.
if [ -f "credentials.json" ]; then
    log "credentials.json found."
    log "Running Google API auth setup..."
    $PYTHON scripts/auth_setup.py || warn "Auth setup had issues — see above."
else
    warn "credentials.json not found!"
    echo ""
    echo "  To set up Google APIs (no gcloud CLI needed):"
    echo "  1. Go to: https://console.cloud.google.com"
    echo "  2. Create a project (or select an existing one)"
    echo "  3. Enable these APIs: Gmail API, Google Sheets API, Google Drive API"
    echo "  4. Go to 'Credentials' > 'Create Credentials' > 'OAuth 2.0 Client ID'"
    echo "  5. Choose 'Desktop app' as application type"
    echo "  6. Download as credentials.json and place in: $(pwd)"
    echo ""
    echo "  Then run: python scripts/auth_setup.py"
fi

# ---------------------------------------------------------------------------
# 7. Verify scripts are executable
# ---------------------------------------------------------------------------
chmod +x scripts/setup.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your credentials"
echo "  2. Place credentials.json in this directory (from Google Cloud Console)"
echo "  3. Edit config.yaml: set sender_name and sender_email"
echo "  4. Run: python scripts/auth_setup.py            # Set up Google auth (no gcloud needed)"
echo ""
echo "Then run:"
echo "  source venv/bin/activate"
echo "  python scripts/auth_setup.py --test              # Verify Google API access"
echo "  python crm/setup_crm.py                         # Create Google Sheets CRM"
echo "  python leads/scrapers/google_maps_leads.py --category 'shop thoi trang' --city 'Ho Chi Minh' --count 30"
echo "  python leads/qualify_leads.py --input leads/data/<file>.csv"
echo "  python outreach/send_sequence.py --dry-run      # Preview emails"
echo ""
echo "Full docs: README.md"
echo ""
