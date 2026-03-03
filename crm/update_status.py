#!/usr/bin/env python3
"""
update_status.py - Update the status and notes for a lead in the CRM.

Usage:
    python update_status.py \
        --business-name "Cửa hàng ABC" \
        --status "Contacted" \
        --notes "Sent intro email, waiting for reply"

Valid status values:
    New | Contacted | Replied | Meeting | Proposal Sent | Closed Won | Closed Lost
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_DIR = Path.home() / "sea-automation-agency"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
ENV_PATH = BASE_DIR / ".env"

VALID_STATUSES = [
    "New",
    "Contacted",
    "Replied",
    "Meeting",
    "Proposal Sent",
    "Closed Won",
    "Closed Lost",
]

# Column indices (0-based) in the Leads sheet
COL_BUSINESS_NAME = 0
COL_STATUS = 9
COL_LAST_CONTACT_DATE = 10
COL_NOTES = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_credentials():
    paths_to_try = [
        CREDENTIALS_PATH,
        Path("credentials.json"),
        Path(__file__).parent / "credentials.json",
    ]
    for path in paths_to_try:
        if path.exists():
            return service_account.Credentials.from_service_account_file(
                str(path), scopes=SCOPES
            )
    print("ERROR: credentials.json not found. See README.md.")
    sys.exit(1)


def load_spreadsheet_id():
    env = dotenv_values(str(ENV_PATH))
    sheet_id = env.get("SHEETS_CRM_ID", "").strip()
    if not sheet_id:
        sheet_id = os.environ.get("SHEETS_CRM_ID", "").strip()
    if not sheet_id:
        print(
            "ERROR: SHEETS_CRM_ID not found in .env\n"
            "Run setup_crm.py first to create the CRM spreadsheet."
        )
        sys.exit(1)
    return sheet_id


def col_letter(index):
    """Convert 0-based column index to A1 letter."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def find_lead_row(service, spreadsheet_id, business_name):
    """
    Search the Leads sheet for a row matching business_name (column A).
    Returns the 1-based row number, or None if not found.
    """
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="'Leads'!A:A",
        )
        .execute()
    )
    values = result.get("values", [])

    search_name = business_name.strip().lower()
    for i, row in enumerate(values):
        if row and row[0].strip().lower() == search_name:
            return i + 1  # 1-based row number

    return None


def update_status(args):
    # Validate status
    if args.status not in VALID_STATUSES:
        print(
            f"ERROR: '{args.status}' is not a valid status.\n"
            f"Valid options: {', '.join(VALID_STATUSES)}"
        )
        sys.exit(1)

    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = load_spreadsheet_id()

    row_number = find_lead_row(service, spreadsheet_id, args.business_name)
    if row_number is None:
        print(f"ERROR: Lead '{args.business_name}' not found in the Leads sheet.")
        sys.exit(1)

    today = datetime.today().strftime("%Y-%m-%d")

    # Build batch update: Status (col J), Last Contact Date (col K), Notes (col M)
    status_col = col_letter(COL_STATUS)         # J
    date_col = col_letter(COL_LAST_CONTACT_DATE)  # K
    notes_col = col_letter(COL_NOTES)           # M

    updates = [
        {
            "range": f"'Leads'!{status_col}{row_number}",
            "values": [[args.status]],
        },
        {
            "range": f"'Leads'!{date_col}{row_number}",
            "values": [[today]],
        },
    ]

    if args.notes:
        updates.append(
            {
                "range": f"'Leads'!{notes_col}{row_number}",
                "values": [[args.notes]],
            }
        )

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": updates},
    ).execute()

    print(f"Updated lead '{args.business_name}' (row {row_number}):")
    print(f"  Status          : {args.status}")
    print(f"  Last Contact    : {today}")
    if args.notes:
        print(f"  Notes           : {args.notes}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Update a lead's status and notes in the SEA Agency CRM."
    )
    parser.add_argument(
        "--business-name",
        required=True,
        help="Business name to look up in the Leads sheet",
    )
    parser.add_argument(
        "--status",
        required=True,
        help=(
            "New status. One of: "
            + ", ".join(VALID_STATUSES)
        ),
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional notes to append/update",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    update_status(args)
