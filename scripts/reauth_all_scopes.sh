#!/usr/bin/env bash
# reauth_all_scopes.sh — Re-authenticate with ALL required Google API scopes
# (Gmail send + read, Sheets, Drive) in a single token.
#
# Run this once. After that, all scripts (email, CRM, reports) will work
# with the same token.json.

set -e

cd ~/sea-automation-agency

echo "=== Google OAuth — All Scopes ==="
echo ""

if [ ! -f credentials.json ]; then
    echo "ERROR: credentials.json not found. Cannot proceed."
    exit 1
fi

if [ -f token.json ]; then
    echo "Backing up current token.json to token.json.backup"
    cp token.json token.json.backup
    rm token.json
    echo "Old token removed."
else
    echo "No existing token.json found."
fi

echo ""
echo "A browser window will open for Google login."
echo "Grant access to Gmail, Google Sheets, and Drive when prompted."
echo ""

python3 -c "
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0, open_browser=True)

with open('token.json', 'w') as f:
    f.write(creds.to_json())

print()
print('Scopes granted:')
for s in creds.scopes:
    print(f'  - {s}')
print()
print('token.json saved with all scopes.')
"

echo ""
echo "Done! All scripts (email, CRM, reports) should now work."
