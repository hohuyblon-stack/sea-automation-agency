#!/usr/bin/env python3
"""
generate_monthly_report.py - Generate and optionally email the monthly client report.

Delegates to the client's reporting_dashboard/main.py for report generation,
then emails the HTML report to the client via Gmail.

Usage:
    python reports/generate_monthly_report.py --client-name shop_thoi_trang_a --month 2026-03
    python reports/generate_monthly_report.py --client-name shop_thoi_trang_a --send-email
    python reports/generate_monthly_report.py --all-clients --month 2026-03

This script:
    1. Finds the client directory under clients/
    2. Calls the reporting dashboard to generate HTML report
    3. Optionally emails the HTML report to the client
    4. Updates the CRM Clients sheet with "Next Report Due" date
"""

import argparse
import base64
import json
import logging
import os
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

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
CLIENTS_DIR = BASE_DIR / "clients"
TOKEN_PATH = BASE_DIR / "token.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def load_env() -> dict:
    env = dotenv_values(str(ENV_PATH))
    for key in ["SENDER_EMAIL", "SENDER_NAME"]:
        if not env.get(key):
            env[key] = os.environ.get(key, "")
    return env


def get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                logger.error("credentials.json not found — cannot send email")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def load_client_data(client_slug: str) -> dict:
    """Load client_data.json from the client directory."""
    client_dir = CLIENTS_DIR / client_slug
    json_path = client_dir / "client_data.json"

    if not client_dir.exists():
        logger.error(f"Client directory not found: {client_dir}")
        sys.exit(1)

    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)

    # Fall back to config.json
    config_path = client_dir / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
            return cfg.get("client", {})

    return {"business_name": client_slug}


def generate_report(client_slug: str, year: int, month: int) -> str:
    """
    Generate the monthly HTML report for a client.
    Returns path to the generated HTML file.
    """
    client_dir = CLIENTS_DIR / client_slug
    report_dir = client_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Try importing the dashboard from the client's directory
    sys.path.insert(0, str(client_dir))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reporting_dashboard",
            str(client_dir / "main.py"),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            # Change CWD to client dir so config.json is found
            original_cwd = os.getcwd()
            os.chdir(str(client_dir))
            spec.loader.exec_module(module)

            config = module.load_config("config.json")
            dashboard = module.ReportingDashboard(config, output_dir=str(report_dir))
            html_path = dashboard.monthly_report(year, month)
            os.chdir(original_cwd)
            return html_path
    except Exception as e:
        logger.warning(f"Could not run client's main.py: {e}. Generating basic report.")

    # Fallback: import from delivery templates
    sys.path.insert(0, str(BASE_DIR / "delivery" / "templates" / "reporting_dashboard"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reporting_dashboard",
            str(BASE_DIR / "delivery" / "templates" / "reporting_dashboard" / "main.py"),
        )
        spec.loader.exec_module(module := importlib.util.module_from_spec(spec))

        # Create a minimal config
        minimal_config = {
            "client": load_client_data(client_slug),
            "storage": {"orders_db": str(client_dir / "data" / "orders.db")},
            "reporting": {"daily_report_time": "09:00"},
        }
        dashboard = module.ReportingDashboard(minimal_config, output_dir=str(report_dir))
        return dashboard.monthly_report(year, month)
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        sys.exit(1)
    finally:
        os.chdir(original_cwd if 'original_cwd' in locals() else str(BASE_DIR))


def email_report(
    gmail_service,
    to_email: str,
    client_name: str,
    html_path: str,
    month: int,
    year: int,
    sender_email: str,
    sender_name: str,
):
    """Send the monthly HTML report as an email attachment."""
    subject = f"Báo Cáo Tháng {month}/{year} — {client_name}"

    body = (
        f"Kính gửi {client_name},\n\n"
        f"Dưới đây là báo cáo hiệu suất tự động hóa tháng {month}/{year} của bạn.\n\n"
        f"Báo cáo bao gồm:\n"
        f"- Tổng số đơn hàng được xử lý tự động\n"
        f"- Doanh thu và so sánh với tháng trước\n"
        f"- Phân tích theo sàn thương mại\n"
        f"- Thời gian tiết kiệm được\n\n"
        f"Nếu bạn có câu hỏi về báo cáo hoặc cần điều chỉnh hệ thống, "
        f"vui lòng liên hệ mình qua Zalo hoặc email này.\n\n"
        f"Trân trọng,\n{sender_name}"
    )

    message = MIMEMultipart()
    message["to"] = to_email
    message["from"] = sender_email
    message["subject"] = subject

    message.attach(MIMEText(body, "plain", "utf-8"))

    # Attach HTML report
    html_file = Path(html_path)
    if html_file.exists():
        with open(html_file, "rb") as f:
            attachment = MIMEBase("text", "html")
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                f"attachment; filename={html_file.name}",
            )
            message.attach(attachment)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        result = gmail_service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info(f"Report emailed to {to_email} — message ID: {result.get('id')}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def list_clients() -> list:
    """Return list of client slugs in clients/ directory."""
    if not CLIENTS_DIR.exists():
        return []
    return [
        d.name for d in CLIENTS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]


def main():
    parser = argparse.ArgumentParser(description="Generate monthly client reports")
    parser.add_argument("--client-name", default="", help="Client directory slug (e.g. shop_thoi_trang_a)")
    parser.add_argument("--all-clients", action="store_true", help="Generate reports for all clients")
    parser.add_argument("--month", default="", help="Month as YYYY-MM (default: current month)")
    parser.add_argument("--send-email", action="store_true", help="Email the report to the client")
    parser.add_argument("--open", action="store_true", help="Open HTML in browser")
    args = parser.parse_args()

    config = load_config()
    env = load_env()

    # Parse month
    today = date.today()
    if args.month:
        parts = args.month.split("-")
        year, month = int(parts[0]), int(parts[1])
    else:
        year, month = today.year, today.month

    # Determine which clients to report on
    clients = []
    if args.all_clients:
        clients = list_clients()
        if not clients:
            print("No client directories found in clients/")
            sys.exit(0)
    elif args.client_name:
        clients = [args.client_name]
    else:
        parser.error("Provide --client-name or --all-clients")

    gmail_service = None
    if args.send_email:
        gmail_service = get_gmail_service()

    for client_slug in clients:
        print(f"\nGenerating report for: {client_slug} ({year}-{month:02d})")

        html_path = generate_report(client_slug, year, month)
        print(f"Report saved: {html_path}")

        if args.send_email and gmail_service:
            client_data = load_client_data(client_slug)
            to_email = client_data.get("email", "")
            if not to_email:
                logger.warning(f"No email for {client_slug} — skipping email send")
            else:
                sender = env.get("SENDER_EMAIL") or config.get("outreach", {}).get("sender_email", "")
                sender_name = env.get("SENDER_NAME") or config.get("outreach", {}).get("sender_name", "")
                email_report(
                    gmail_service=gmail_service,
                    to_email=to_email,
                    client_name=client_data.get("business_name", client_slug),
                    html_path=html_path,
                    month=month,
                    year=year,
                    sender_email=sender,
                    sender_name=sender_name,
                )

        if args.open:
            import subprocess
            subprocess.run(["open", html_path])

    print(f"\nDone. {len(clients)} report(s) generated.")


if __name__ == "__main__":
    main()
