#!/usr/bin/env python3
"""
auth_setup.py - Set up Google API authentication for SEA Automation Agency.

This script handles OAuth2 authentication directly using Google's Python client
libraries. It does NOT require gcloud CLI, gws, or any external auth tools.

Usage:
    python scripts/auth_setup.py

    # Test authentication after setup
    python scripts/auth_setup.py --test

    # Re-authenticate (clear existing tokens)
    python scripts/auth_setup.py --reauth

Requirements:
    - credentials.json in the project root (download from Google Cloud Console)
    - pip install google-auth google-auth-oauthlib google-api-python-client
"""

import argparse
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"

# All scopes needed by the agency pipeline
ALL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def log(msg):
    print(f"{GREEN}[AUTH]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}[WARN]{NC}  {msg}")


def error(msg):
    print(f"{RED}[ERROR]{NC} {msg}")
    sys.exit(1)


def check_credentials_file():
    """Verify credentials.json exists and is valid."""
    if not CREDENTIALS_PATH.exists():
        error(
            f"credentials.json not found at {CREDENTIALS_PATH}\n\n"
            "  To set up Google API credentials (no gcloud CLI needed):\n"
            "  1. Go to https://console.cloud.google.com\n"
            "  2. Create a project (or select an existing one)\n"
            "  3. Enable these APIs:\n"
            "     - Gmail API\n"
            "     - Google Sheets API\n"
            "     - Google Drive API\n"
            "  4. Go to 'Credentials' > 'Create Credentials' > 'OAuth 2.0 Client ID'\n"
            "  5. Choose 'Desktop app' as the application type\n"
            "  6. Download the JSON file and save it as:\n"
            f"     {CREDENTIALS_PATH}\n"
        )

    try:
        with open(CREDENTIALS_PATH) as f:
            data = json.load(f)
        if "installed" not in data and "web" not in data:
            error(
                "credentials.json does not look like an OAuth2 client credentials file.\n"
                "Make sure you downloaded OAuth 2.0 Client ID credentials (not a service account key)."
            )
        log("credentials.json found and valid.")
    except json.JSONDecodeError:
        error("credentials.json is not valid JSON.")


def authenticate(force_reauth=False):
    """Run the OAuth2 flow and save tokens."""
    creds = None

    if TOKEN_PATH.exists() and not force_reauth:
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)
        except Exception:
            warn("Existing token.json is invalid, will re-authenticate.")
            creds = None

    if creds and creds.valid:
        log("Already authenticated (token.json is valid).")
        return creds

    if creds and creds.expired and creds.refresh_token:
        log("Token expired, refreshing...")
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            log("Token refreshed successfully.")
            return creds
        except Exception as e:
            warn(f"Token refresh failed: {e}")
            warn("Will re-authenticate from scratch.")

    # Full OAuth flow
    log("Starting OAuth2 authentication...")
    log("A browser window will open for you to sign in with your Google account.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_PATH), ALL_SCOPES
    )
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    log(f"Authentication successful! Token saved to {TOKEN_PATH}")
    return creds


def test_auth(creds):
    """Test that authentication works by making simple API calls."""
    print()
    log("Testing API access...")

    # Test Gmail
    try:
        gmail = build("gmail", "v1", credentials=creds)
        profile = gmail.users().getProfile(userId="me").execute()
        log(f"  Gmail OK - authenticated as: {profile['emailAddress']}")
    except Exception as e:
        warn(f"  Gmail FAILED: {e}")

    # Test Sheets
    try:
        sheets = build("sheets", "v4", credentials=creds)
        sheets.spreadsheets().create(
            body={"properties": {"title": "__auth_test__"}},
            fields="spreadsheetId",
        ).execute()
        log("  Google Sheets OK - can create spreadsheets")
    except Exception as e:
        # Permission denied is expected if Drive scope wasn't granted
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            warn(f"  Google Sheets: limited access (may need to enable Sheets API)")
        else:
            warn(f"  Google Sheets FAILED: {e}")

    # Test Drive
    try:
        drive = build("drive", "v3", credentials=creds)
        drive.files().list(pageSize=1).execute()
        log("  Google Drive OK - can list files")
    except Exception as e:
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            warn(f"  Google Drive: limited access (may need to enable Drive API)")
        else:
            warn(f"  Google Drive FAILED: {e}")

    print()
    log("Auth test complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Set up Google API authentication for SEA Automation Agency"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test authentication after setup"
    )
    parser.add_argument(
        "--reauth", action="store_true",
        help="Force re-authentication (clear existing tokens)"
    )
    args = parser.parse_args()

    print()
    log("=== SEA Automation Agency — Google Auth Setup ===")
    log("No gcloud CLI or external tools required!")
    print()

    # Step 1: Check credentials.json
    check_credentials_file()

    # Step 2: Authenticate
    if args.reauth and TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        log("Cleared existing token.json")

    creds = authenticate(force_reauth=args.reauth)

    # Step 3: Test if requested
    if args.test:
        test_auth(creds)
    else:
        print()
        log("Run with --test to verify API access:")
        log(f"  python {Path(__file__).name} --test")

    print()
    log("Done! You can now run the agency scripts.")
    print()


if __name__ == "__main__":
    main()
