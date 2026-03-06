#!/usr/bin/env python3
"""
zalo_sequence.py - Send the 3-message Zalo outreach sequence via OpenClaw.

Reads qualified leads from CSV, determines which message to send next based on
state tracking, then sends via OpenClaw's zalouser channel (personal account).

Usage:
    # Preview messages without sending
    python zalo_sequence.py --input leads/data/qualified_2026-03-04.csv --dry-run

    # Print messages for manual copy-paste
    python zalo_sequence.py --input leads/data/qualified_2026-03-04.csv --print

    # Send via OpenClaw (requires gateway running + Zalo authenticated)
    python zalo_sequence.py --input leads/data/qualified_2026-03-04.csv --send

    # Send to a single number
    python zalo_sequence.py --phone "0901234567" --name "Nguyen Van A" --business "Shop ABC" --send

Requirements:
    - OpenClaw installed and gateway running (openclaw gateway)
    - Zalo authenticated (openclaw channels login --channel zalouser)
    - pip install python-dotenv pyyaml
"""

import argparse
import csv
import json
import logging
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from dotenv import dotenv_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path.home() / "sea-automation-agency"
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.yaml"
TEMPLATES_DIR = BASE_DIR / "outreach" / "templates"
STATE_PATH = BASE_DIR / "outreach" / ".zalo_sequence_state.json"

# Sequence: (message_number, days_after_previous)
SEQUENCE = [
    (1, 0),
    (2, 4),
    (3, 10),
]


# ---------------------------------------------------------------------------
# Config / env
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env = dotenv_values(str(ENV_PATH))
    for key in ["SENDER_NAME", "SENDER_EMAIL", "SENDER_ZALO"]:
        if key not in env:
            env[key] = ""
    return env


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# State tracking (local JSON — no CRM dependency)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def get_lead_state(state: dict, key: str) -> dict:
    return state.get(key, {})


def update_lead_state(state: dict, key: str, msg_num: int, sent_date: str) -> dict:
    lead_state = {**state.get(key, {})}
    lead_state[f"zalo_{msg_num}_sent"] = True
    lead_state[f"zalo_{msg_num}_date"] = sent_date
    return {**state, key: lead_state}


# ---------------------------------------------------------------------------
# Sequence logic
# ---------------------------------------------------------------------------

def determine_next_message(lead_state: dict) -> Optional[int]:
    if lead_state.get("replied"):
        return None

    today = date.today()

    msg1_sent = lead_state.get("zalo_1_sent", False)
    msg2_sent = lead_state.get("zalo_2_sent", False)
    msg3_sent = lead_state.get("zalo_3_sent", False)

    if not msg1_sent:
        return 1

    if msg1_sent and not msg2_sent:
        date_str = lead_state.get("zalo_1_date", "")
        if date_str:
            try:
                sent = datetime.strptime(date_str, "%Y-%m-%d").date()
                return 2 if today >= sent + timedelta(days=4) else None
            except ValueError:
                pass
        return 2

    if msg2_sent and not msg3_sent:
        date_str = lead_state.get("zalo_2_date", "")
        if date_str:
            try:
                sent = datetime.strptime(date_str, "%Y-%m-%d").date()
                return 3 if today >= sent + timedelta(days=6) else None
            except ValueError:
                pass
        return 3

    return None  # sequence complete


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def load_template(msg_num: int) -> str:
    template_map = {
        1: "zalo_1_cold_vi.md",
        2: "zalo_2_followup_vi.md",
        3: "zalo_3_breakup_vi.md",
    }
    filename = template_map.get(msg_num)
    if not filename:
        raise FileNotFoundError(f"No Zalo template for message {msg_num}")
    path = TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Zalo template not found: {path}")
    content = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()


def render_template(template: str, variables: dict) -> str:
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def build_template_vars(lead: dict, env: dict, config: dict) -> dict:
    outreach_cfg = config.get("outreach", {})
    return {
        "business_name": lead.get("business_name", ""),
        "contact_name": lead.get("contact_name", "") or "Anh/Chi",
        "platform": lead.get("platform", "").replace("_", " ").title() or "Shopee/TikTok Shop",
        "monthly_orders": lead.get("monthly_orders", "500+") or "500+",
        "sender_name": env.get("SENDER_NAME") or outreach_cfg.get("sender_name", ""),
        "sender_zalo": env.get("SENDER_ZALO", ""),
        "sender_email": env.get("SENDER_EMAIL", ""),
    }


# ---------------------------------------------------------------------------
# OpenClaw sending
# ---------------------------------------------------------------------------

def check_openclaw_ready() -> bool:
    """Check if OpenClaw gateway is running and Zalo is authenticated."""
    try:
        result = subprocess.run(
            ["openclaw", "health"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.error("OpenClaw gateway is not running. Start it: openclaw gateway")
            return False
        return True
    except FileNotFoundError:
        logger.error("openclaw not found. Install: npm install -g openclaw@latest")
        return False
    except subprocess.TimeoutExpired:
        logger.error("OpenClaw gateway not responding")
        return False


def validate_zalo_phone(phone: str) -> bool:
    """Validate Vietnam Zalo phone number format.

    Accepts formats like:
    - 0901234567 (10-11 digits starting with 0)
    - +84 90 123 4567 (with country code and spaces)
    - 84901234567 (country code without +)
    - +84-90-123-4567 (with hyphens)
    """
    # Remove spaces, hyphens, and + from input
    normalized = re.sub(r"[\s\+\-]", "", phone)
    if normalized.startswith("84"):
        normalized = "0" + normalized[2:]

    # Must be 10-11 digits starting with 0
    return bool(re.match(r"^0[0-9]{9,10}$", normalized))


def validate_zalo_message(message: str) -> bool:
    """Validate Zalo message format.

    Rejects messages that are empty, too long, or look like injection attempts.
    """
    if not message or len(message) > 1000:
        return False
    # Reject if it looks like a flag injection attempt (starts with -)
    if message.strip().startswith("-"):
        return False
    return True


def send_via_openclaw(phone: str, message: str, dry_run: bool = False) -> bool:
    """Send a Zalo message via OpenClaw CLI.

    Validates inputs before passing to subprocess to prevent injection attacks.
    """
    # Validate inputs
    if not validate_zalo_phone(phone):
        logger.error(f"Invalid phone number format: {phone}")
        return False

    if not validate_zalo_message(message):
        logger.error(f"Invalid message format or length")
        return False

    # Normalize phone number
    phone = re.sub(r"[\s\+\-]", "", phone)
    if phone.startswith("84"):
        phone = "0" + phone[2:]

    cmd = [
        "openclaw", "message", "send",
        "--channel", "zalouser",
        "--target", phone,
        "--message", message,
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True
        logger.error(f"OpenClaw send failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"OpenClaw send timed out for {phone}")
        return False


# ---------------------------------------------------------------------------
# Lead processing
# ---------------------------------------------------------------------------

def get_lead_key(lead: dict) -> str:
    return lead.get("business_name", lead.get("phone", lead.get("zalo", "unknown")))


def process_lead(
    lead: dict,
    state: dict,
    env: dict,
    config: dict,
    mode: str = "dry-run",
    force_msg: Optional[int] = None,
) -> tuple:
    """
    Process one lead. Returns (updated_state, was_sent).
    mode: 'dry-run' | 'print' | 'send'
    """
    key = get_lead_key(lead)
    phone = lead.get("zalo", "") or lead.get("phone", "")
    business_name = lead.get("business_name", key)

    if not phone:
        logger.warning(f"No phone/zalo for '{business_name}' — skipping")
        return state, False

    lead_state = get_lead_state(state, key)
    next_msg = force_msg or determine_next_message(lead_state)

    if next_msg is None:
        logger.info(f"'{business_name}': sequence complete or too early — skipping")
        return state, False

    try:
        template = load_template(next_msg)
    except FileNotFoundError as e:
        logger.error(str(e))
        return state, False

    vars_ = build_template_vars(lead, env, config)
    message = render_template(template, vars_)
    today_str = date.today().isoformat()

    if mode == "dry-run":
        print(f"\n{'='*60}")
        print(f"DRY RUN — Zalo {next_msg} to: {business_name} ({phone})")
        print(f"{'='*60}")
        print(message)
        print(f"{'='*60}")
        return state, True

    if mode == "print":
        print(f"\n{'='*60}")
        print(f"[Zalo {next_msg}] {business_name} — {phone}")
        print(f"{'='*60}")
        print(message)
        print(f"{'='*60}")
        new_state = update_lead_state(state, key, next_msg, today_str)
        return new_state, True

    # mode == "send" — use OpenClaw
    logger.info(f"Sending Zalo {next_msg} to '{business_name}' ({phone})")
    sent = send_via_openclaw(phone, message)

    if sent:
        logger.info("Sent!")
        new_state = update_lead_state(state, key, next_msg, today_str)
        return new_state, True

    logger.error(f"Failed to send to {phone}")
    return state, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Send Zalo outreach sequence via OpenClaw")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Preview without sending or saving state")
    group.add_argument("--print", action="store_true", dest="print_mode", help="Print messages for manual copy-paste (saves state)")
    group.add_argument("--send", action="store_true", help="Send via OpenClaw zalouser channel")

    parser.add_argument("--input", default="", help="Qualified leads CSV file")
    parser.add_argument("--phone", default="", help="Single phone number")
    parser.add_argument("--name", default="", help="Contact name (for single send)")
    parser.add_argument("--business", default="", help="Business name (for single send)")
    parser.add_argument("--platform", default="Shopee", help="Platform (for single send)")
    parser.add_argument("--msg-num", type=int, choices=[1, 2, 3], help="Force a specific message number")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between sends (default: 5)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Default to dry-run if no mode specified
    if not args.print_mode and not args.send:
        args.dry_run = True

    mode = "send" if args.send else ("print" if args.print_mode else "dry-run")

    # Check OpenClaw is ready before attempting to send
    if mode == "send" and not check_openclaw_ready():
        print("\nRun the setup first: bash zalo_openclaw_setup.sh")
        sys.exit(1)

    if mode == "print":
        print("\nPRINT MODE: Messages below are ready to copy-paste into Zalo.")
        print("State will be saved after printing.\n")

    config = load_config()
    env = load_env()
    state = load_state()

    # Build leads list
    leads = []
    if args.phone:
        leads = [{
            "business_name": args.business or args.name or args.phone,
            "contact_name": args.name,
            "phone": args.phone,
            "zalo": args.phone,
            "platform": args.platform,
            "monthly_orders": "500+",
        }]
    elif args.input:
        path = Path(args.input)
        if not path.exists():
            logger.error(f"Input file not found: {args.input}")
            sys.exit(1)
        with open(path, newline="", encoding="utf-8") as f:
            leads = list(csv.DictReader(f))
        logger.info(f"Loaded {len(leads)} leads from {args.input}")
    else:
        parser.error("Provide --input or --phone")

    sent = skipped = 0
    for lead in leads:
        state, was_sent = process_lead(
            lead=lead,
            state=state,
            env=env,
            config=config,
            mode=mode,
            force_msg=args.msg_num,
        )
        if was_sent:
            sent += 1
            if mode == "send" and len(leads) > 1:
                time.sleep(args.delay)
        else:
            skipped += 1

    if mode in ("print", "send") and sent > 0:
        save_state(state)
        logger.info(f"State saved to {STATE_PATH}")

    print(f"\nDone. Sent/printed: {sent}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
