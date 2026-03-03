#!/usr/bin/env python3
"""
add_lead.py - Add a new lead to the SEA Agency CRM.

Usage:
    python add_lead.py \
        --name "Cửa hàng ABC" \
        --contact "Nguyễn Văn A" \
        --email "contact@abc.vn" \
        --phone "0901234567" \
        --platform "Shopee" \
        --city "Ho Chi Minh" \
        --monthly-orders 800 \
        --pain-point "Overwhelmed by manual order processing" \
        --score 8

Returns the row number added to the Leads sheet.
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
        # Fallback: check real environment variable
        sheet_id = os.environ.get("SHEETS_CRM_ID", "").strip()
    if not sheet_id:
        print(
            "ERROR: SHEETS_CRM_ID not found in .env\n"
            "Run setup_crm.py first to create the CRM spreadsheet."
        )
        sys.exit(1)
    return sheet_id


def get_next_empty_row(service, spreadsheet_id, sheet_name):
    """Return the index of the first empty row (1-based)."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A:A")
        .execute()
    )
    values = result.get("values", [])
    return len(values) + 1  # next row after last filled row


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def add_lead(args):
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = load_spreadsheet_id()

    today = datetime.today().strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Build the Leads row
    # Columns: Business Name, Contact Name, Email, Phone, Platform, City,
    #          Monthly Orders (Est), Pain Point, Lead Score, Status,
    #          Last Contact Date, Deal Value (VND), Notes
    # ------------------------------------------------------------------
    leads_row = [
        args.name,
        args.contact,
        args.email,
        args.phone,
        args.platform,
        args.city,
        args.monthly_orders,
        args.pain_point,
        args.score,
        "New",       # Default status
        today,       # Last Contact Date
        "",          # Deal Value (VND) - filled later
        "",          # Notes
    ]

    # Find next empty row in Leads
    leads_next_row = get_next_empty_row(service, spreadsheet_id, "Leads")

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'Leads'!A{leads_next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [leads_row]},
    ).execute()

    print(f"Lead added to Leads sheet at row {leads_next_row}.")

    # ------------------------------------------------------------------
    # Build the Outreach Tracker row
    # Columns: Business Name, Email 1 Sent, Email 1 Date, Email 2 Sent,
    #          Email 2 Date, Email 3 Sent, Email 3 Date, Reply Received,
    #          Reply Date, Meeting Booked, Meeting Date
    # ------------------------------------------------------------------
    outreach_row = [
        args.name,
        "No",   # Email 1 Sent
        "",     # Email 1 Date
        "No",   # Email 2 Sent
        "",     # Email 2 Date
        "No",   # Email 3 Sent
        "",     # Email 3 Date
        "No",   # Reply Received
        "",     # Reply Date
        "No",   # Meeting Booked
        "",     # Meeting Date
    ]

    outreach_next_row = get_next_empty_row(service, spreadsheet_id, "Outreach Tracker")

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'Outreach Tracker'!A{outreach_next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [outreach_row]},
    ).execute()

    print(f"Outreach entry added to Outreach Tracker at row {outreach_next_row}.")

    print(f"\nRow number in Leads sheet: {leads_next_row}")
    return leads_next_row


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Add a new lead to the SEA Agency CRM."
    )
    parser.add_argument("--name", required=True, help="Business name")
    parser.add_argument("--contact", required=True, help="Contact person name")
    parser.add_argument("--email", required=True, help="Email address")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument(
        "--platform", default="", help="Platform (Shopee, TikTok Shop, etc.)"
    )
    parser.add_argument("--city", default="", help="City")
    parser.add_argument(
        "--monthly-orders", default="", help="Estimated monthly orders"
    )
    parser.add_argument("--pain-point", default="", help="Main pain point")
    parser.add_argument(
        "--score", default="", help="Lead score (1-10)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    add_lead(args)
