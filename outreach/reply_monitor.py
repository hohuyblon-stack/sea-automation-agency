#!/usr/bin/env python3
"""
reply_monitor.py - Monitor Gmail for replies from outreach leads.

Polls Gmail inbox every N minutes, detects replies from leads,
sends a macOS desktop notification + optional Zalo webhook alert,
and updates the lead CSV status to "replied".

Usage:
    # Run once (check now)
    python reply_monitor.py --once

    # Run as daemon, check every 5 minutes
    python reply_monitor.py --interval 5

    # Check against a specific leads file
    python reply_monitor.py --input leads/data/qualified_2026-03-04.csv --once

Requirements:
    - token.json from Gmail OAuth (run send_sequence.py first to auth)
    - credentials.json in project root
"""

import argparse
import base64
import csv
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import yaml
from dotenv import dotenv_values
from google.auth.transport.requests import Request
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
LEADS_DIR = BASE_DIR / "leads" / "data"
STATE_FILE = BASE_DIR / "outreach" / ".reply_monitor_state.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                logger.error(f"credentials.json not found at {CREDENTIALS_PATH}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# State (tracks which message IDs we've already seen)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen_message_ids": [], "replied_emails": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Lead loading
# ---------------------------------------------------------------------------

def load_lead_emails(leads_dir: Path) -> dict:
    """
    Returns a dict mapping lowercase email -> business_name
    for all leads across all CSV files.
    """
    email_map = {}
    for csv_file in leads_dir.glob("*.csv"):
        try:
            with open(csv_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    email = row.get("email", "").strip().lower()
                    business = row.get("business_name", "").strip()
                    if email and business:
                        email_map[email] = business
        except Exception as e:
            logger.warning(f"Could not read {csv_file}: {e}")
    return email_map


def update_lead_status_in_csv(leads_dir: Path, email: str, new_status: str):
    """Update the status column for a lead in any CSV file."""
    for csv_file in leads_dir.glob("*.csv"):
        rows = []
        updated = False
        try:
            with open(csv_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                if not fieldnames or "email" not in fieldnames:
                    continue
                for row in reader:
                    if row.get("email", "").strip().lower() == email.lower():
                        row["status"] = new_status
                        updated = True
                    rows.append(row)
        except Exception:
            continue

        if updated:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"Updated status to '{new_status}' for {email} in {csv_file.name}")


# ---------------------------------------------------------------------------
# Gmail polling
# ---------------------------------------------------------------------------

def get_sender_email(gmail_service) -> str:
    """Get the authenticated user's email address."""
    profile = gmail_service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def extract_sender_email(headers: list) -> str:
    """Extract the From email address from message headers."""
    for h in headers:
        if h["name"].lower() == "from":
            value = h["value"]
            # Parse "Name <email>" or just "email"
            if "<" in value and ">" in value:
                return value.split("<")[1].split(">")[0].strip().lower()
            return value.strip().lower()
    return ""


def extract_subject(headers: list) -> str:
    for h in headers:
        if h["name"].lower() == "subject":
            return h["value"]
    return "(no subject)"


def check_for_replies(gmail_service, lead_emails: dict, state: dict) -> list:
    """
    Poll Gmail inbox for messages from lead email addresses.
    Returns list of new reply dicts: {email, business_name, subject, message_id, snippet}
    """
    new_replies = []
    seen_ids = set(state.get("seen_message_ids", []))

    try:
        # Search inbox for messages from any lead email
        email_list = " OR ".join([f"from:{e}" for e in list(lead_emails.keys())[:50]])
        query = f"({email_list}) in:inbox"

        result = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=50,
        ).execute()

        messages = result.get("messages", [])

        for msg_ref in messages:
            msg_id = msg_ref["id"]
            if msg_id in seen_ids:
                continue

            # Fetch full message
            msg = gmail_service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            sender_email = extract_sender_email(headers)
            subject = extract_subject(headers)
            snippet = msg.get("snippet", "")

            # Check if sender is one of our leads
            if sender_email in lead_emails:
                business_name = lead_emails[sender_email]
                new_replies.append({
                    "email": sender_email,
                    "business_name": business_name,
                    "subject": subject,
                    "snippet": snippet,
                    "message_id": msg_id,
                    "timestamp": datetime.now().isoformat(),
                })
                logger.info(f"New reply from {business_name} <{sender_email}>: {subject}")

            seen_ids.add(msg_id)

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")

    state["seen_message_ids"] = list(seen_ids)
    return new_replies


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_macos(title: str, message: str, subtitle: str = ""):
    """Send a macOS desktop notification via osascript.

    Properly escapes user input to prevent AppleScript injection.
    """
    def escape_applescript(s: str) -> str:
        """Escape special characters for AppleScript string literals."""
        return s.replace('\\', '\\\\').replace('"', '\\"')

    title_esc = escape_applescript(title)
    message_esc = escape_applescript(message)
    subtitle_esc = escape_applescript(subtitle) if subtitle else ""

    parts = [f'display notification "{message_esc}" with title "{title_esc}"']
    if subtitle:
        parts.append(f'subtitle "{subtitle_esc}"')
    parts.append('sound name "Ping"')

    script = ' with '.join(parts)

    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        logger.info(f"Desktop notification sent: {title_esc}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Desktop notification failed: {e}")


def notify_zalo(webhook_url: str, message: str):
    """Send a Zalo webhook notification."""
    if not webhook_url:
        return
    try:
        payload = {"text": message}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Zalo notification sent")
        else:
            logger.warning(f"Zalo webhook returned {resp.status_code}: {resp.text}")
    except requests.RequestException as e:
        logger.warning(f"Zalo notification failed: {e}")


def send_notifications(reply: dict, zalo_webhook: str):
    """Send all notifications for a new reply."""
    business = reply["business_name"]
    email = reply["email"]
    subject = reply["subject"]
    snippet = reply["snippet"]

    # macOS desktop notification
    notify_macos(
        title=f"Reply from {business}",
        message=snippet[:100] if snippet else subject,
        subtitle=email,
    )

    # Zalo notification
    if zalo_webhook:
        zalo_msg = (
            f"[SEA Agency] Reply received!\n"
            f"From: {business} <{email}>\n"
            f"Subject: {subject}\n"
            f"Preview: {snippet[:150]}"
        )
        notify_zalo(zalo_webhook, zalo_msg)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env = dotenv_values(str(ENV_PATH))
    for key in ["ZALO_WEBHOOK_URL", "SENDER_EMAIL"]:
        if key not in env:
            env[key] = os.environ.get(key, "")
    return env


def run_check(gmail_service, leads_dir: Path, state: dict, zalo_webhook: str) -> int:
    """Run one check cycle. Returns number of new replies found."""
    lead_emails = load_lead_emails(leads_dir)
    if not lead_emails:
        logger.warning("No lead emails found in CSV files")
        return 0

    logger.info(f"Monitoring {len(lead_emails)} lead emails...")
    new_replies = check_for_replies(gmail_service, lead_emails, state)

    already_replied = set(state.get("replied_emails", []))

    for reply in new_replies:
        email = reply["email"]
        if email in already_replied:
            continue

        send_notifications(reply, zalo_webhook)
        update_lead_status_in_csv(leads_dir, email, "replied")
        already_replied.add(email)
        logger.info(f"Processed reply from {reply['business_name']}")

    state["replied_emails"] = list(already_replied)
    save_state(state)

    if new_replies:
        logger.info(f"Found {len(new_replies)} new reply(ies)")
    else:
        logger.info("No new replies")

    return len(new_replies)


def main():
    parser = argparse.ArgumentParser(description="Monitor Gmail for lead replies")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=5, help="Check interval in minutes (default: 5)")
    parser.add_argument("--input", default="", help="Specific leads CSV (default: all CSVs in leads/data)")
    args = parser.parse_args()

    env = load_env()
    zalo_webhook = env.get("ZALO_WEBHOOK_URL", "")
    leads_dir = Path(args.input).parent if args.input else LEADS_DIR

    gmail_service = get_gmail_service()
    state = load_state()

    if args.once:
        run_check(gmail_service, leads_dir, state, zalo_webhook)
        return

    logger.info(f"Reply monitor started — checking every {args.interval} minutes")
    logger.info("Press Ctrl+C to stop")

    while True:
        try:
            run_check(gmail_service, leads_dir, state, zalo_webhook)
            time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            logger.info("Monitor stopped")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
