#!/usr/bin/env python3
"""
generate_proposal.py - Generate a client proposal from a Markdown template.

Fills in {{variable}} placeholders and outputs both Markdown and HTML versions.

Usage:
    python generate_proposal.py \
        --template proposals/templates/order_sync_proposal.md \
        --client-data '{"client_name":"Nguyen Van A","business_name":"Shop Thoi Trang A","platform":"Shopee","monthly_orders":"800","pain_point":"Xu ly don hang thu cong mat 4 gio moi ngay"}' \
        --output-dir generated/

    python generate_proposal.py \
        --template proposals/templates/order_sync_proposal.md \
        --client-json clients/shop_a/client_data.json \
        --output-dir generated/

Outputs:
    generated/proposal_shop_thoi_trang_a_2026-03-03.md
    generated/proposal_shop_thoi_trang_a_2026-03-03.html
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import date
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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def load_env() -> dict:
    env = dotenv_values(str(ENV_PATH))
    for key in ["SENDER_EMAIL", "SENDER_NAME", "SENDER_ZALO"]:
        if not env.get(key):
            env[key] = os.environ.get(key, "")
    return env


def compute_derived_vars(client_data: dict) -> dict:
    """Compute derived variables from client data."""
    try:
        monthly_orders = int(str(client_data.get("monthly_orders", "500")).replace(",", ""))
    except ValueError:
        monthly_orders = 500

    # Rough estimate: 5 minutes per order manual processing
    manual_hours_per_month = round(monthly_orders * 5 / 60)
    manual_hours_per_day = round(manual_hours_per_month / 22, 1)  # 22 working days

    # Labor cost saved (100K VND/hour)
    labor_cost_saved_vnd = f"{manual_hours_per_month * 100_000:,.0f}".replace(",", ".")

    # Generate proposal ID
    today = date.today()
    business_slug = re.sub(r"\W+", "", client_data.get("business_name", "client"))[:10].upper()
    proposal_id = f"SEA-{today.strftime('%Y%m%d')}-{business_slug}"

    return {
        "manual_hours_per_month": manual_hours_per_month,
        "manual_hours_per_day": manual_hours_per_day,
        "labor_cost_saved_vnd": labor_cost_saved_vnd,
        "proposal_id": proposal_id,
        "proposal_date": today.strftime("%d/%m/%Y"),
    }


def render_template(template_text: str, variables: dict) -> str:
    """Replace all {{key}} placeholders. Warn about unfilled ones."""
    result = template_text
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", str(value))

    # Warn about remaining placeholders
    remaining = re.findall(r"\{\{(\w+)\}\}", result)
    if remaining:
        unique = list(dict.fromkeys(remaining))
        logger.warning(f"Unfilled placeholders: {unique}")

    return result


def md_to_html(markdown_text: str, title: str = "Proposal") -> str:
    """
    Simple Markdown to HTML conversion.
    Uses markdown library if available, falls back to basic regex conversion.
    """
    try:
        import markdown
        body = markdown.markdown(
            markdown_text,
            extensions=["tables", "nl2br"],
        )
    except ImportError:
        # Basic fallback
        html = markdown_text
        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        # Italic
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        # Code
        html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        # Horizontal rule
        html = re.sub(r"^---$", r"<hr>", html, flags=re.MULTILINE)
        # Paragraphs
        html = re.sub(r"\n\n+", r"</p><p>", html)
        html = f"<p>{html}</p>"
        body = html

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.6; }}
  h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 8px; }}
  h2 {{ color: #283593; margin-top: 2em; }}
  h3 {{ color: #3949ab; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th {{ background: #1a237e; color: white; padding: 10px; text-align: left; }}
  td {{ padding: 8px 10px; border: 1px solid #ddd; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  blockquote {{ border-left: 4px solid #1a237e; margin: 0; padding: 10px 20px; background: #e8eaf6; font-style: italic; }}
  hr {{ border: none; border-top: 2px solid #e0e0e0; margin: 2em 0; }}
  code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
  strong {{ color: #1a237e; }}
  .footer {{ margin-top: 3em; padding-top: 1em; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


CASE_STUDY_SECTION_MD = """

---

## DỰ ÁN ĐÃ TRIỂN KHAI / Past Projects

Mình đã triển khai các hệ thống tự động hóa cho doanh nghiệp Việt Nam. Xem chi tiết:

- **Tự Động Hóa Báo Cáo Email** — Hệ thống báo cáo doanh thu tự động hàng ngày, tiết kiệm 45 phút/ngày.
  [Xem case study](generated/case_studies/email_reporting.html)

- **Bot Telegram Quản Lý Gara** — Check-in xe từ 5 phút xuống 30 giây, dữ liệu tập trung real-time.
  [Xem case study](generated/case_studies/garage_telegram_bot.html)

*We've deployed automation systems for Vietnamese businesses. See full case studies above.*

---
"""


def generate_proposal(
    template_path: str,
    client_data: dict,
    output_dir: str,
    config: dict,
    env: dict,
    include_case_studies: bool = False,
) -> tuple[str, str]:
    """
    Generate proposal files.
    Returns (md_path, html_path).
    """
    # Load template
    path = Path(template_path)
    if not path.exists():
        logger.error(f"Template not found: {template_path}")
        sys.exit(1)
    template_text = path.read_text(encoding="utf-8")

    # Inject case studies section before the contact/footer section
    if include_case_studies:
        # Insert before the last "## 7." or "## THÔNG TIN LIÊN HỆ" section
        contact_patterns = [
            r"(## 7\. THÔNG TIN LIÊN HỆ)",
            r"(## \d+\. THÔNG TIN LIÊN HỆ)",
            r"(## THÔNG TIN LIÊN HỆ)",
        ]
        inserted = False
        for pattern in contact_patterns:
            if re.search(pattern, template_text):
                template_text = re.sub(
                    pattern,
                    CASE_STUDY_SECTION_MD + r"\1",
                    template_text,
                    count=1,
                )
                inserted = True
                logger.info("Case studies section inserted into proposal")
                break
        if not inserted:
            # Fallback: append before the last horizontal rule
            template_text += CASE_STUDY_SECTION_MD
            logger.info("Case studies section appended to proposal")

    # Build variable dict
    outreach_cfg = config.get("outreach", {})
    services = {s["id"]: s for s in config.get("services", [])}

    # Find matching service
    service_id = client_data.get("service_id", "order_sync")
    service = services.get(service_id, {})

    derived = compute_derived_vars(client_data)

    variables = {
        # Client info
        "client_name": client_data.get("client_name", ""),
        "business_name": client_data.get("business_name", ""),
        "platform": client_data.get("platform", "Shopee"),
        "monthly_orders": client_data.get("monthly_orders", "500"),
        "pain_point": client_data.get("pain_point", ""),
        "city": client_data.get("city", ""),
        # Sender info
        "sender_name": env.get("SENDER_NAME") or outreach_cfg.get("sender_name", ""),
        "sender_email": env.get("SENDER_EMAIL") or outreach_cfg.get("sender_email", ""),
        "sender_zalo": env.get("SENDER_ZALO", ""),
        # Service pricing
        "service_name": service.get("name", ""),
        "service_name_vi": service.get("name_vi", ""),
        "price_vnd": f"{service.get('price_vnd', 15_000_000):,}".replace(",", "."),
        "price_usd": service.get("price_usd", 600),
        "delivery_days": service.get("delivery_days", 7),
        # Derived
        **derived,
    }

    # Render
    rendered = render_template(template_text, variables)

    # Build output filename
    os.makedirs(output_dir, exist_ok=True)
    business_slug = re.sub(r"\s+", "_", client_data.get("business_name", "client").lower())
    business_slug = re.sub(r"[^\w]", "", business_slug)
    today = date.today().isoformat()
    base_name = f"proposal_{business_slug}_{today}"

    md_path = os.path.join(output_dir, f"{base_name}.md")
    html_path = os.path.join(output_dir, f"{base_name}.html")

    # Save Markdown
    Path(md_path).write_text(rendered, encoding="utf-8")
    logger.info(f"Markdown saved: {md_path}")

    # Save HTML
    html_content = md_to_html(rendered, title=f"Proposal – {client_data.get('business_name', '')}")
    Path(html_path).write_text(html_content, encoding="utf-8")
    logger.info(f"HTML saved: {html_path}")

    return md_path, html_path


def main():
    parser = argparse.ArgumentParser(description="Generate a client proposal from a Markdown template")
    parser.add_argument("--template", required=True, help="Path to proposal template .md")
    parser.add_argument("--client-data", default="", help="JSON string of client data")
    parser.add_argument("--client-json", default="", help="Path to client data JSON file")
    parser.add_argument("--output-dir", default="generated", help="Output directory (default: generated/)")
    parser.add_argument("--open", action="store_true", help="Open HTML in browser after generation")
    parser.add_argument(
        "--case-studies",
        action="store_true",
        help="Include links to case study pages in the proposal",
    )
    args = parser.parse_args()

    config = load_config()
    env = load_env()

    # Load client data
    client_data = {}
    if args.client_json:
        path = Path(args.client_json)
        if not path.exists():
            logger.error(f"Client JSON not found: {args.client_json}")
            sys.exit(1)
        client_data = json.loads(path.read_text())
    elif args.client_data:
        try:
            client_data = json.loads(args.client_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in --client-data: {e}")
            sys.exit(1)
    else:
        parser.error("Provide --client-data or --client-json")

    md_path, html_path = generate_proposal(
        template_path=args.template,
        client_data=client_data,
        output_dir=args.output_dir,
        config=config,
        env=env,
        include_case_studies=args.case_studies,
    )

    print(f"\nProposal generated:")
    print(f"  Markdown: {md_path}")
    print(f"  HTML:     {html_path}")

    if args.open:
        import subprocess
        subprocess.run(["open", html_path])


if __name__ == "__main__":
    main()
