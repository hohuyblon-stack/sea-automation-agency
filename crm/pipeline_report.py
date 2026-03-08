#!/usr/bin/env python3
"""
pipeline_report.py - Print a terminal dashboard for the SEA Agency CRM.

Usage:
    python pipeline_report.py

Shows:
  - Lead funnel breakdown by status
  - Proposal breakdown by status
  - Active client count and total MRR
  - Outreach follow-ups due today
"""

import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import dotenv_values

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
BASE_DIR = Path.home() / "sea-automation-agency"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
ENV_PATH = BASE_DIR / ".env"

# Column indices (0-based) ---- Leads sheet
L_STATUS = 9

# Column indices (0-based) ---- Outreach Tracker sheet
OT_BUSINESS_NAME = 0
OT_EMAIL1_SENT = 1
OT_EMAIL1_DATE = 2
OT_EMAIL2_SENT = 3
OT_EMAIL2_DATE = 4
OT_EMAIL3_SENT = 5
OT_REPLY_RECEIVED = 7

# Column indices (0-based) ---- Proposals sheet
P_STATUS = 5

# Column indices (0-based) ---- Clients sheet
C_MONTHLY_RETAINER = 4


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


def get_sheet_values(service, spreadsheet_id, sheet_name):
    """Fetch all rows from a sheet (skipping header row)."""
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A:Z",
        )
        .execute()
    )
    rows = result.get("values", [])
    return rows[1:] if len(rows) > 1 else []  # skip header


def safe_get(row, index, default=""):
    try:
        return row[index]
    except IndexError:
        return default


def parse_date(date_str):
    """Try to parse common date formats. Returns a date object or None."""
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def format_vnd(value):
    """Format a number as VND with commas."""
    try:
        cleaned = str(value).replace(",", "").replace(".", "").strip()
        num = int(float(cleaned))
        return f"{num:,}"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def build_leads_section(leads_rows):
    status_counts = {}
    for row in leads_rows:
        status = safe_get(row, L_STATUS, "Unknown").strip() or "Unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    order = [
        "New",
        "Contacted",
        "Replied",
        "Meeting",
        "Proposal Sent",
        "Closed Won",
        "Closed Lost",
    ]
    lines = ["LEADS"]
    visible = {k: v for k, v in status_counts.items() if k in order}
    others = {k: v for k, v in status_counts.items() if k not in order}

    all_items = [(s, visible.get(s, 0)) for s in order if visible.get(s, 0) > 0]
    all_items += [(k, v) for k, v in others.items()]

    for i, (status, count) in enumerate(all_items):
        prefix = "└──" if i == len(all_items) - 1 else "├──"
        lines.append(f"  {prefix} {status}: {count}")

    if not all_items:
        lines.append("  └── (no leads yet)")

    return lines


def build_proposals_section(proposals_rows):
    status_counts = {}
    for row in proposals_rows:
        status = safe_get(row, P_STATUS, "Unknown").strip() or "Unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    order = ["Draft", "Sent", "Negotiating", "Won", "Lost"]
    lines = ["PROPOSALS"]
    all_items = [(s, status_counts[s]) for s in order if s in status_counts]
    all_items += [(k, v) for k, v in status_counts.items() if k not in order]

    for i, (status, count) in enumerate(all_items):
        prefix = "└──" if i == len(all_items) - 1 else "├──"
        lines.append(f"  {prefix} {status}: {count}")

    if not all_items:
        lines.append("  └── (no proposals yet)")

    return lines


def build_clients_section(clients_rows):
    active_count = len(clients_rows)
    total_mrr = 0
    for row in clients_rows:
        retainer_str = safe_get(row, C_MONTHLY_RETAINER, "0")
        try:
            cleaned = str(retainer_str).replace(",", "").replace(".", "").strip()
            total_mrr += int(float(cleaned))
        except (ValueError, TypeError):
            pass

    lines = [
        "CLIENTS",
        f"  ├── Active: {active_count}",
        f"  └── MRR: {format_vnd(total_mrr)} VND",
    ]
    return lines


def build_followups_section(outreach_rows):
    """
    Determine which leads need follow-up today based on outreach timing rules:
      - Email 2 should be sent ~4 days after Email 1
      - Email 3 should be sent ~10 days after Email 1
    """
    today = date.today()
    followups = []

    for row in outreach_rows:
        business_name = safe_get(row, OT_BUSINESS_NAME, "").strip()
        if not business_name:
            continue

        reply_received = safe_get(row, OT_REPLY_RECEIVED, "No").strip().lower()
        if reply_received in ("yes", "true", "1"):
            continue  # No need to follow up, they replied

        email1_sent = safe_get(row, OT_EMAIL1_SENT, "No").strip().lower()
        email1_date_str = safe_get(row, OT_EMAIL1_DATE, "").strip()
        email2_sent = safe_get(row, OT_EMAIL2_SENT, "No").strip().lower()
        email3_sent = safe_get(row, OT_EMAIL3_SENT, "No").strip().lower()

        # Check if Email 2 is due
        if email1_sent in ("yes", "true", "1") and email2_sent not in ("yes", "true", "1"):
            email1_date = parse_date(email1_date_str)
            if email1_date:
                days_since = (today - email1_date).days
                if days_since >= 4:
                    followups.append((days_since, business_name, "send email_2"))

        # Check if Email 3 is due
        elif email2_sent in ("yes", "true", "1") and email3_sent not in ("yes", "true", "1"):
            email1_date = parse_date(email1_date_str)
            if email1_date:
                days_since = (today - email1_date).days
                if days_since >= 10:
                    followups.append((days_since, business_name, "send email_3"))

    lines = ["FOLLOW-UPS DUE TODAY"]
    if not followups:
        lines.append("  └── (no follow-ups due)")
    else:
        for i, (days, name, action) in enumerate(followups):
            prefix = "└──" if i == len(followups) - 1 else "├──"
            lines.append(f"  {prefix} [Day {days}] {name} - {action}")

    return lines


# ---------------------------------------------------------------------------
# Dashboard printer
# ---------------------------------------------------------------------------

SEPARATOR = "─" * 40


def print_dashboard(leads_rows, proposals_rows, clients_rows, outreach_rows):
    today_str = datetime.today().strftime("%Y-%m-%d")

    print()
    print("╔══════════════════════════════════════╗")
    print("║      SEA AGENCY PIPELINE REPORT      ║")
    print(f"║           {today_str}              ║")
    print("╚══════════════════════════════════════╝")
    print()

    sections = [
        build_leads_section(leads_rows),
        build_proposals_section(proposals_rows),
        build_clients_section(clients_rows),
        build_followups_section(outreach_rows),
    ]

    for section_lines in sections:
        for line in section_lines:
            print(line)
        print()

    # Summary stats
    total_leads = len(leads_rows)
    won_proposals = sum(
        1
        for row in proposals_rows
        if safe_get(row, P_STATUS, "").strip() == "Won"
    )
    print(SEPARATOR)
    print(f"Total Leads in CRM : {total_leads}")
    print(f"Proposals Won      : {won_proposals}")
    print(f"Active Clients     : {len(clients_rows)}")
    print(SEPARATOR)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = load_spreadsheet_id()

    leads_rows = get_sheet_values(service, spreadsheet_id, "Leads")
    proposals_rows = get_sheet_values(service, spreadsheet_id, "Proposals")
    clients_rows = get_sheet_values(service, spreadsheet_id, "Clients")
    outreach_rows = get_sheet_values(service, spreadsheet_id, "Outreach Tracker")

    print_dashboard(leads_rows, proposals_rows, clients_rows, outreach_rows)


if __name__ == "__main__":
    main()
