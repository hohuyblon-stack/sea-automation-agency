#!/usr/bin/env bash
# fix_crm_auth.sh — Re-authenticate Google API with Sheets + Drive scopes
# The current token.json only has Gmail scopes; CRM needs spreadsheets + drive.
#
# This will:
# 1. Back up the current token.json (Gmail-only)
# 2. Delete it so setup_crm.py triggers a fresh OAuth consent
# 3. Run setup_crm.py which will open a browser for Google login
#
# After this, token.json will have spreadsheets + drive scopes.
# You'll need to re-run send_sequence.py auth separately if you need Gmail again.

set -e

cd ~/sea-automation-agency

echo "=== Fix CRM Authentication ==="
echo ""

if [ ! -f credentials.json ]; then
    echo "ERROR: credentials.json not found. Cannot proceed."
    exit 1
fi

if [ -f token.json ]; then
    echo "Backing up current token.json (Gmail-only) to token.json.gmail_backup"
    cp token.json token.json.gmail_backup
    rm token.json
    echo "Old token removed."
else
    echo "No existing token.json found."
fi

echo ""
echo "Running CRM setup — a browser window will open for Google login."
echo "Grant access to Google Sheets and Drive when prompted."
echo ""

export PERSONAL_GOOGLE_EMAIL="hohuyblon@gmail.com"
python3 crm/setup_crm.py

echo ""
echo "Done! CRM should now be accessible."
echo ""
echo "NOTE: The new token only has Sheets/Drive scopes."
echo "If you need Gmail sending later, you may need to re-auth with combined scopes."
