#!/usr/bin/env python3
"""
setup_crm.py - Create and configure the SEA Agency CRM Google Spreadsheet.

Usage:
    python setup_crm.py

Requirements:
    - credentials.json in ~/sea-automation-agency/ or current directory
    - google-auth, google-api-python-client installed
"""

import os
import sys
import json
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BASE_DIR = Path.home() / "sea-automation-agency"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
ENV_PATH = BASE_DIR / ".env"
SPREADSHEET_TITLE = "SEA Agency CRM"

# Sheet definitions: (tab name, [column headers])
SHEETS = [
    (
        "Leads",
        [
            "Business Name",
            "Contact Name",
            "Email",
            "Phone",
            "Platform",
            "City",
            "Monthly Orders (Est)",
            "Pain Point",
            "Lead Score",
            "Status",
            "Last Contact Date",
            "Deal Value (VND)",
            "Notes",
        ],
    ),
    (
        "Outreach Tracker",
        [
            "Business Name",
            "Email 1 Sent",
            "Email 1 Date",
            "Email 2 Sent",
            "Email 2 Date",
            "Email 3 Sent",
            "Email 3 Date",
            "Reply Received",
            "Reply Date",
            "Meeting Booked",
            "Meeting Date",
        ],
    ),
    (
        "Proposals",
        [
            "Client Name",
            "Business Name",
            "Service",
            "Proposal Date",
            "Value (VND)",
            "Status",
            "Follow Up Date",
            "Notes",
        ],
    ),
    (
        "Clients",
        [
            "Client Name",
            "Business Name",
            "Service",
            "Start Date",
            "Monthly Retainer",
            "Next Report Due",
            "Health Score (1-5)",
            "Notes",
        ],
    ),
    (
        "Revenue",
        [
            "Month",
            "New MRR",
            "Churned MRR",
            "Total MRR",
            "One-time Revenue",
            "Total Revenue",
            "# Clients",
        ],
    ),
]

# Status dropdown options per sheet
STATUS_VALIDATIONS = {
    "Leads": {
        "col_index": 9,  # column J (0-indexed)
        "values": [
            "New",
            "Contacted",
            "Replied",
            "Meeting",
            "Proposal Sent",
            "Closed Won",
            "Closed Lost",
        ],
    },
    "Proposals": {
        "col_index": 5,  # column F (0-indexed)
        "values": ["Draft", "Sent", "Negotiating", "Won", "Lost"],
    },
}

# Header background colors (R, G, B as 0-1 floats)
HEADER_COLORS = {
    "Leads": {"red": 0.133, "green": 0.357, "blue": 0.608},          # dark blue
    "Outreach Tracker": {"red": 0.204, "green": 0.596, "blue": 0.329}, # green
    "Proposals": {"red": 0.612, "green": 0.153, "blue": 0.690},       # purple
    "Clients": {"red": 0.902, "green": 0.494, "blue": 0.133},         # orange
    "Revenue": {"red": 0.204, "green": 0.533, "blue": 0.533},         # teal
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_credentials():
    """Load service account credentials from credentials.json."""
    paths_to_try = [
        CREDENTIALS_PATH,
        Path("credentials.json"),
        Path(__file__).parent / "credentials.json",
    ]
    for path in paths_to_try:
        if path.exists():
            print(f"Loading credentials from: {path}")
            return service_account.Credentials.from_service_account_file(
                str(path), scopes=SCOPES
            )
    print(
        "ERROR: credentials.json not found.\n"
        "Place your Google service account JSON at:\n"
        f"  {CREDENTIALS_PATH}\n"
        "See README.md for setup instructions."
    )
    sys.exit(1)


def col_letter(index):
    """Convert 0-based column index to A1 letter notation."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def create_spreadsheet(service):
    """Create a new Google Spreadsheet with all required tabs."""
    sheet_bodies = []
    for i, (name, _) in enumerate(SHEETS):
        sheet_bodies.append(
            {
                "properties": {
                    "title": name,
                    "sheetId": i,
                    "index": i,
                    "gridProperties": {"rowCount": 1000, "columnCount": 26},
                }
            }
        )

    body = {
        "properties": {"title": SPREADSHEET_TITLE},
        "sheets": sheet_bodies,
    }

    spreadsheet = (
        service.spreadsheets().create(body=body, fields="spreadsheetId,spreadsheetUrl").execute()
    )
    return spreadsheet["spreadsheetId"], spreadsheet["spreadsheetUrl"]


def write_headers(service, spreadsheet_id):
    """Write header rows to each sheet."""
    data = []
    for name, headers in SHEETS:
        data.append(
            {
                "range": f"'{name}'!A1:{col_letter(len(headers) - 1)}1",
                "values": [headers],
            }
        )

    body = {"valueInputOption": "RAW", "data": data}
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    print("Headers written.")


def format_headers(service, spreadsheet_id):
    """Apply bold + background color to header row of each sheet."""
    requests = []
    for sheet_index, (name, headers) in enumerate(SHEETS):
        color = HEADER_COLORS.get(name, {"red": 0.5, "green": 0.5, "blue": 0.5})
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_index,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {
                                    "red": 1.0,
                                    "green": 1.0,
                                    "blue": 1.0,
                                },
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            }
        )
        # Freeze header row
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_index,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )
        # Auto-resize columns
        requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_index,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(headers),
                    }
                }
            }
        )

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()
    print("Header formatting applied.")


def add_data_validation(service, spreadsheet_id):
    """Add dropdown validation for Status columns."""
    requests = []

    for sheet_index, (name, _) in enumerate(SHEETS):
        if name not in STATUS_VALIDATIONS:
            continue

        validation = STATUS_VALIDATIONS[name]
        col_idx = validation["col_index"]
        dropdown_values = validation["values"]

        requests.append(
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_index,
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": col_idx,
                        "endColumnIndex": col_idx + 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": v} for v in dropdown_values
                            ],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            }
        )

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
        print("Data validation (dropdowns) added.")


def share_spreadsheet(spreadsheet_id: str, email: str):
    """Share the spreadsheet with a personal Google account so it's accessible."""
    drive_service = build("drive", "v3", credentials=get_credentials())
    drive_service.permissions().create(
        fileId=spreadsheet_id,
        body={"type": "user", "role": "writer", "emailAddress": email},
        sendNotificationEmail=False,
    ).execute()
    print(f"Spreadsheet shared with: {email}")


def save_env(spreadsheet_id):
    """Append or update SHEETS_CRM_ID in the .env file."""
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().splitlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("SHEETS_CRM_ID="):
            new_lines.append(f"SHEETS_CRM_ID={spreadsheet_id}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"SHEETS_CRM_ID={spreadsheet_id}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n")
    print(f"Spreadsheet ID saved to {ENV_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== SEA Agency CRM Setup ===\n")

    personal_email = os.environ.get("PERSONAL_GOOGLE_EMAIL", "").strip()
    if not personal_email:
        personal_email = input("Enter your personal Google email to share the CRM with: ").strip()
    if not personal_email:
        print("WARNING: No personal email provided — you may not be able to open the spreadsheet.")

    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)

    print("Creating spreadsheet...")
    spreadsheet_id, spreadsheet_url = create_spreadsheet(service)
    print(f"Spreadsheet created: {spreadsheet_id}")

    write_headers(service, spreadsheet_id)
    format_headers(service, spreadsheet_id)
    add_data_validation(service, spreadsheet_id)
    save_env(spreadsheet_id)

    if personal_email:
        print(f"Sharing with {personal_email}...")
        share_spreadsheet(spreadsheet_id, personal_email)

    print("\n=== Setup Complete ===")
    print(f"CRM URL: {spreadsheet_url}")


if __name__ == "__main__":
    main()
