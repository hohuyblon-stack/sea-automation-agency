#!/usr/bin/env python3
"""
send_sequence.py - Send the 3-email outreach sequence via Gmail API.

Reads qualified leads from CSV, checks the CRM Outreach Tracker to determine
which email in the sequence to send next, then sends via Gmail.

Usage:
    # Preview without sending
    python send_sequence.py --dry-run

    # Send from a specific leads CSV
    python send_sequence.py --input leads/data/qualified_2026-03-03.csv

    # Send to a single email
    python send_sequence.py --to "contact@shop.vn" --name "Nguyen Van A" --business "Shop ABC"

    # Use Vietnamese templates (default)
    python send_sequence.py --lang vi

    # Use English templates
    python send_sequence.py --lang en

Requirements:
    - Gmail API OAuth2 credentials.json in project root
    - SHEETS_CRM_ID in .env (for CRM tracking)
    - pip install google-auth google-auth-oauthlib google-api-python-client python-dotenv
"""

import argparse
import base64
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import markdown as md_lib
import yaml
from dotenv import dotenv_values
from google.auth.transport.requests import Request, AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path.home() / "sea-automation-agency"
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.yaml"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
TEMPLATES_DIR = BASE_DIR / "outreach" / "templates"

# Workaround: google-api-python-client >=2.x escapes '!' as '\!' in URIs,
# breaking Sheets range queries like 'Sheet!A1:B2'. Patch it out.
import googleapiclient.http as _ghttp
_orig_execute = _ghttp.HttpRequest.execute
def _patched_execute(self, *a, **kw):
    if self.uri and '%5C%21' in self.uri:
        self.uri = self.uri.replace('%5C%21', '%21')
    return _orig_execute(self, *a, **kw)
_ghttp.HttpRequest.execute = _patched_execute

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sequence: (email_number, template_prefix, days_from_start)
SEQUENCE = [
    (1, "email_1_cold", 0),
    (2, "email_2_followup", 4),
    (3, "email_3_breakup", 10),
]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def load_env() -> dict:
    env = dotenv_values(str(ENV_PATH))
    # Merge real env vars as fallback
    for key in ["SHEETS_CRM_ID", "SENDER_EMAIL", "SENDER_NAME", "SENDER_ZALO"]:
        if key not in env:
            env[key] = os.environ.get(key, "")
    return env


def validate_input_path(input_path: str, allowed_dir: str = "leads/data") -> Path:
    """Validate that input path is within allowed directory.

    Prevents path traversal attacks by ensuring the resolved path is within
    the allowed directory.

    Args:
        input_path: User-provided file path
        allowed_dir: Subdirectory path relative to BASE_DIR

    Returns:
        Resolved Path object if valid

    Raises:
        ValueError: If path is outside allowed directory
        FileNotFoundError: If file does not exist
    """
    path = Path(input_path).resolve()
    allowed = (BASE_DIR / allowed_dir).resolve()

    # Ensure path is within allowed directory
    try:
        path.relative_to(allowed)
    except ValueError:
        raise ValueError(f"Path must be within {allowed_dir} directory, got: {input_path}")

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix != ".csv":
        raise ValueError(f"Only CSV files allowed, got: {path.suffix}")

    return path


# ---------------------------------------------------------------------------
# Gmail auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                logger.error(
                    f"credentials.json not found at {CREDENTIALS_PATH}\n"
                    "Download it from Google Cloud Console > OAuth 2.0 Credentials."
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_sheets_session() -> Optional[AuthorizedSession]:
    """Return an AuthorizedSession for Sheets API using OAuth token."""
    if not TOKEN_PATH.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    if not creds.valid:
        creds.refresh(Request())
    return AuthorizedSession(creds)


SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(Exception):
    pass


def _sheets_get(session: AuthorizedSession, spreadsheet_id: str, range_: str) -> list:
    """GET a range from Sheets. Returns rows list or []."""
    from urllib.parse import quote
    url = f"{SHEETS_BASE}/{spreadsheet_id}/values/{quote(range_, safe='')}"
    r = session.get(url)
    if r.status_code != 200:
        raise SheetsError(f"{r.status_code} {r.text[:200]}")
    return r.json().get("values", [])


def _sheets_batch_update(session: AuthorizedSession, spreadsheet_id: str, data: list):
    """Batch update ranges in Sheets."""
    url = f"{SHEETS_BASE}/{spreadsheet_id}/values:batchUpdate"
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    r = session.post(url, json=body)
    if r.status_code != 200:
        raise SheetsError(f"{r.status_code} {r.text[:200]}")


def _sheets_update(session: AuthorizedSession, spreadsheet_id: str, range_: str, values: list):
    """Update a single range in Sheets."""
    from urllib.parse import quote
    url = f"{SHEETS_BASE}/{spreadsheet_id}/values/{quote(range_, safe='!:')}?valueInputOption=USER_ENTERED"
    r = session.put(url, json={"values": values})
    if r.status_code != 200:
        raise SheetsError(f"{r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def load_template(sequence_num: int, lang: str) -> dict:
    """
    Load email template. Returns dict with keys: subject, body, frontmatter.
    """
    template_map = {
        1: f"email_1_cold_{lang}.md",
        2: f"email_2_followup_{lang}.md",
        3: f"email_3_breakup_{lang}.md",
    }
    filename = template_map.get(sequence_num)
    if not filename:
        raise ValueError(f"No template for sequence {sequence_num}")

    path = TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")

    content = path.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = parts[2].strip()

    return {
        "subject": frontmatter.get("subject", f"Email {sequence_num}"),
        "body": body,
        "frontmatter": frontmatter,
    }


def render_template(template: dict, variables: dict) -> dict:
    """Replace {{variable}} placeholders in subject and body."""
    subject = template["subject"]
    body = template["body"]

    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        subject = subject.replace(placeholder, str(value))
        body = body.replace(placeholder, str(value))

    return {"subject": subject, "body": body}


def build_template_vars(lead: dict, config: dict, env: dict) -> dict:
    """Build the variable dict for template rendering."""
    outreach_cfg = config.get("outreach", {})
    return {
        "business_name": lead.get("business_name", ""),
        "contact_name": lead.get("contact_name", "") or "Anh/Chị",
        "platform": lead.get("platform", "").replace("_", " ").title() or "Shopee/TikTok Shop",
        "monthly_orders": lead.get("monthly_orders", "500+") or "500+",
        "sender_name": env.get("SENDER_NAME") or outreach_cfg.get("sender_name", ""),
        "sender_email": env.get("SENDER_EMAIL") or outreach_cfg.get("sender_email", ""),
        "sender_zalo": env.get("SENDER_ZALO", ""),
    }


# ---------------------------------------------------------------------------
# Gmail sending
# ---------------------------------------------------------------------------

def create_message(to: str, subject: str, body: str, sender: str) -> dict:
    """Create a Gmail API message dict."""
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject

    # Plain text part
    text_part = MIMEText(body, "plain", "utf-8")
    message.attach(text_part)

    # HTML version with markdown rendering
    html_body = md_lib.markdown(body, extensions=["nl2br"])
    html_part = MIMEText(f"<html><body style='font-family:sans-serif;font-size:15px;line-height:1.6;max-width:600px;margin:auto;padding:20px;color:#222;'>{html_body}</body></html>", "html", "utf-8")
    message.attach(html_part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def send_email(gmail_service, to: str, subject: str, body: str, sender: str) -> Optional[str]:
    """Send an email via Gmail API. Returns message ID on success."""
    try:
        msg = create_message(to, subject, body, sender)
        result = gmail_service.users().messages().send(userId="me", body=msg).execute()
        return result.get("id")
    except HttpError as e:
        logger.error(f"Gmail send error: {e}")
        return None


# ---------------------------------------------------------------------------
# CRM tracking
# ---------------------------------------------------------------------------

def get_outreach_status(sheets_service, spreadsheet_id: str, business_name: str) -> dict:
    """
    Look up the outreach status for a business in the CRM.
    Returns dict with email_1_sent, email_2_sent, email_3_sent, dates.
    """
    if not sheets_service or not spreadsheet_id:
        return {}

    try:
        rows = _sheets_get(sheets_service, spreadsheet_id, "Outreach Tracker!A:K")
        if len(rows) < 2:
            return {}

        headers = rows[0]
        for row in rows[1:]:
            row_dict = dict(zip(headers, row + [""] * (len(headers) - len(row))))
            if row_dict.get("Business Name", "").strip().lower() == business_name.strip().lower():
                return row_dict
    except SheetsError as e:
        logger.warning(f"CRM lookup failed: {e}")

    return {}


def update_crm_outreach(
    sheets_service,
    spreadsheet_id: str,
    business_name: str,
    sequence_num: int,
    sent_date: str,
):
    """Mark an email as sent in the CRM Outreach Tracker."""
    if not sheets_service or not spreadsheet_id:
        return

    col_map = {
        1: ("B", "C"),   # Email 1 Sent, Email 1 Date
        2: ("D", "E"),   # Email 2 Sent, Email 2 Date
        3: ("F", "G"),   # Email 3 Sent, Email 3 Date
    }
    sent_col, date_col = col_map.get(sequence_num, ("B", "C"))

    try:
        names = [r[0] if r else "" for r in _sheets_get(sheets_service, spreadsheet_id, "Outreach Tracker!A:A")]
        for i, name in enumerate(names):
            if name.strip().lower() == business_name.strip().lower():
                row_num = i + 1
                _sheets_batch_update(sheets_service, spreadsheet_id, [
                    {"range": f"Outreach Tracker!{sent_col}{row_num}", "values": [["Yes"]]},
                    {"range": f"Outreach Tracker!{date_col}{row_num}", "values": [[sent_date]]},
                ])
                logger.debug(f"CRM updated: {business_name} email {sequence_num}")
                return
    except SheetsError as e:
        logger.warning(f"CRM update failed: {e}")


def update_lead_status(sheets_service, spreadsheet_id: str, business_name: str, status: str):
    """Update the Status column in the Leads sheet."""
    if not sheets_service or not spreadsheet_id:
        return
    try:
        names = [r[0] if r else "" for r in _sheets_get(sheets_service, spreadsheet_id, "Leads!A:A")]
        for i, name in enumerate(names):
            if name.strip().lower() == business_name.strip().lower():
                row_num = i + 1
                _sheets_update(sheets_service, spreadsheet_id, f"Leads!J{row_num}", [[status]])
                return
    except SheetsError as e:
        logger.warning(f"Lead status update failed: {e}")


# ---------------------------------------------------------------------------
# Sequence logic
# ---------------------------------------------------------------------------

def determine_next_email(crm_row: dict) -> Optional[int]:
    """
    Given a CRM outreach row, determine which email to send next.
    Returns 1, 2, 3, or None (if sequence is complete or should stop).
    """
    # Stop immediately if the lead has replied or booked a meeting
    replied = crm_row.get("Reply Received", "No").strip().lower() == "yes"
    meeting = crm_row.get("Meeting Booked", "No").strip().lower() == "yes"
    if replied or meeting:
        return None

    email_1_sent = crm_row.get("Email 1 Sent", "No").strip().lower() == "yes"
    email_2_sent = crm_row.get("Email 2 Sent", "No").strip().lower() == "yes"
    email_3_sent = crm_row.get("Email 3 Sent", "No").strip().lower() == "yes"

    today = date.today()

    if not email_1_sent:
        return 1

    if email_1_sent and not email_2_sent:
        email_1_date_str = crm_row.get("Email 1 Date", "")
        if email_1_date_str:
            try:
                email_1_date = datetime.strptime(email_1_date_str, "%Y-%m-%d").date()
                if today >= email_1_date + timedelta(days=4):
                    return 2
                else:
                    return None  # Too early for email 2
            except ValueError:
                pass
        return 2

    if email_2_sent and not email_3_sent:
        email_2_date_str = crm_row.get("Email 2 Date", "")
        if email_2_date_str:
            try:
                email_2_date = datetime.strptime(email_2_date_str, "%Y-%m-%d").date()
                if today >= email_2_date + timedelta(days=6):
                    return 3
                else:
                    return None  # Too early for email 3
            except ValueError:
                pass
        return 3

    return None  # Sequence complete


def process_lead(
    lead: dict,
    gmail_service,
    sheets_service,
    config: dict,
    env: dict,
    lang: str = "vi",
    dry_run: bool = False,
) -> bool:
    """
    Process one lead: determine next email, render, send, update CRM.
    Returns True if email was sent (or would be sent in dry-run).
    """
    business_name = lead.get("business_name", "")
    email = lead.get("email", "").strip()

    if not email:
        logger.warning(f"No email for '{business_name}' — skipping")
        return False

    spreadsheet_id = env.get("SHEETS_CRM_ID", "")
    crm_row = get_outreach_status(sheets_service, spreadsheet_id, business_name)

    # Determine which email to send
    if crm_row:
        next_email = determine_next_email(crm_row)
    else:
        next_email = 1  # No CRM entry = start from email 1

    if next_email is None:
        logger.info(f"'{business_name}': sequence complete or too early — skipping")
        return False

    # Load and render template
    try:
        template = load_template(next_email, lang)
    except FileNotFoundError as e:
        logger.error(str(e))
        return False

    template_vars = build_template_vars(lead, config, env)
    rendered = render_template(template, template_vars)

    sender_email = env.get("SENDER_EMAIL") or config.get("outreach", {}).get("sender_email", "")
    if not sender_email:
        logger.error("SENDER_EMAIL not set in .env or config.yaml")
        return False

    today_str = date.today().isoformat()

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — Email {next_email} to: {business_name} <{email}>")
        print(f"Subject: {rendered['subject']}")
        print(f"{'='*60}")
        print(rendered["body"])
        print(f"{'='*60}")
        return True

    # Send
    logger.info(f"Sending email {next_email} to '{business_name}' <{email}>")
    msg_id = send_email(gmail_service, email, rendered["subject"], rendered["body"], sender_email)

    if msg_id:
        logger.info(f"Sent! Message ID: {msg_id}")
        # Update CRM
        update_crm_outreach(sheets_service, spreadsheet_id, business_name, next_email, today_str)
        update_lead_status(sheets_service, spreadsheet_id, business_name, "Contacted")
        return True
    else:
        logger.error(f"Failed to send to {email}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Send outreach email sequence via Gmail")
    parser.add_argument("--input", default="", help="Qualified leads CSV file")
    parser.add_argument("--to", default="", help="Send to a single email address")
    parser.add_argument("--name", default="", help="Contact name (for single send)")
    parser.add_argument("--business", default="", help="Business name (for single send)")
    parser.add_argument("--platform", default="Shopee", help="Platform (for single send)")
    parser.add_argument("--lang", choices=["vi", "en"], default="vi", help="Email language (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--email-num", type=int, choices=[1, 2, 3], help="Force a specific email number")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between sends (default: 2)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config()
    env = load_env()

    # Auth (skip in dry-run for testing)
    gmail_service = None
    sheets_service = None
    if not args.dry_run:
        gmail_service = get_gmail_service()
        sheets_service = get_sheets_session()

    # Build leads list
    leads = []
    if args.to:
        leads = [{
            "business_name": args.business or args.name or args.to,
            "contact_name": args.name,
            "email": args.to,
            "platform": args.platform,
            "monthly_orders": "500",
        }]
    elif args.input:
        try:
            path = validate_input_path(args.input)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                leads = list(reader)
            logger.info(f"Loaded {len(leads)} leads from {path}")
        except (ValueError, FileNotFoundError) as e:
            logger.error(str(e))
            sys.exit(1)
    else:
        parser.error("Provide --input or --to")

    # Process leads
    sent = 0
    skipped = 0
    for lead in leads:
        result = process_lead(
            lead=lead,
            gmail_service=gmail_service,
            sheets_service=sheets_service,
            config=config,
            env=env,
            lang=args.lang,
            dry_run=args.dry_run,
        )
        if result:
            sent += 1
            if not args.dry_run and len(leads) > 1:
                time.sleep(args.delay)
        else:
            skipped += 1

    print(f"\nDone. Sent: {sent}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
