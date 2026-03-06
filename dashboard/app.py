#!/usr/bin/env python3
"""
SEA Automation Agency — Dashboard Backend
Flask app serving API endpoints for the agency dashboard.
"""

import csv
import glob
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from dotenv import dotenv_values
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_DIR = Path.home() / "sea-automation-agency"
LEADS_DIR = BASE_DIR / "leads" / "data"
TEMPLATES_DIR = BASE_DIR / "outreach" / "templates"
CONFIG_PATH = BASE_DIR / "config.yaml"
ENV_PATH = BASE_DIR / ".env"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        env = dict(dotenv_values(str(ENV_PATH)))
    for key in ["SHEETS_CRM_ID", "SENDER_EMAIL", "SENDER_NAME", "SENDER_ZALO"]:
        if key not in env or not env[key]:
            env[key] = os.environ.get(key, "")
    return env


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_qualified_leads() -> list[dict]:
    files = sorted(glob.glob(str(LEADS_DIR / "qualified_*.csv")))
    if not files:
        return []
    leads = []
    with open(files[-1], newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            leads.append(dict(row))
    return leads


def get_raw_leads() -> list[dict]:
    files = sorted(glob.glob(str(LEADS_DIR / "browser_scraped_*.csv")))
    if not files:
        return []
    leads = []
    with open(files[-1], newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            leads.append(dict(row))
    return leads


def get_sheets_data(tab_name: str):
    """Read a CRM tab via Google Sheets API. Returns list[dict] or None."""
    env = load_env()
    sid = env.get("SHEETS_CRM_ID", "")
    sa_path = BASE_DIR / "service_account.json"
    if not sid or not sa_path.exists():
        return None
    try:
        from google.oauth2 import service_account as sa_mod
        from googleapiclient.discovery import build

        creds = sa_mod.Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        svc = build("sheets", "v4", credentials=creds)
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=f"'{tab_name}'!A:Z")
            .execute()
        )
        rows = result.get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [
            dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in rows[1:]
        ]
    except Exception as e:
        print(f"[Sheets] {tab_name} error: {e}")
        return None


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/leads")
def api_leads():
    leads = get_qualified_leads()

    # Merge CRM data when available
    crm_leads = get_sheets_data("Leads")
    if crm_leads:
        crm_map = {
            l.get("Business Name", "").strip().lower(): l for l in crm_leads
        }
        for lead in leads:
            crm = crm_map.get(lead.get("business_name", "").strip().lower())
            if crm:
                lead["status"] = crm.get("Status", lead.get("status", "new"))
                lead["deal_value"] = crm.get("Deal Value (VND)", "")
                lead["last_contact"] = crm.get("Last Contact Date", "")
                lead["pain_point"] = crm.get("Pain Point", "")

    # Filters
    status_f = request.args.get("status", "")
    platform_f = request.args.get("platform", "")
    search_q = request.args.get("q", "").lower()

    if status_f:
        leads = [l for l in leads if l.get("status", "").lower() == status_f.lower()]
    if platform_f:
        leads = [
            l for l in leads if platform_f.lower() in l.get("platform", "").lower()
        ]
    if search_q:
        leads = [
            l
            for l in leads
            if search_q in l.get("business_name", "").lower()
            or search_q in l.get("email", "").lower()
            or search_q in l.get("city", "").lower()
        ]

    # Sort
    sort_by = request.args.get("sort", "score")
    reverse = request.args.get("order", "desc") == "desc"
    if sort_by == "score":
        leads.sort(key=lambda l: int(l.get("score", 0) or 0), reverse=reverse)
    elif sort_by in ("business_name", "status", "platform", "city", "email"):
        leads.sort(key=lambda l: l.get(sort_by, "").lower(), reverse=reverse)

    return jsonify({"leads": leads, "total": len(leads)})


@app.route("/api/pipeline")
def api_pipeline():
    leads = get_qualified_leads()
    pipeline = {
        "total": len(leads),
        "new": 0,
        "contacted": 0,
        "replied": 0,
        "meeting": 0,
        "proposal_sent": 0,
        "closed_won": 0,
        "closed_lost": 0,
    }

    crm_leads = get_sheets_data("Leads")
    source = crm_leads if crm_leads else leads

    status_key = "Status" if crm_leads else "status"
    for item in source:
        s = item.get(status_key, "new").strip().lower()
        mapped = {
            "new": "new",
            "contacted": "contacted",
            "replied": "replied",
            "meeting": "meeting",
            "proposal sent": "proposal_sent",
            "closed won": "closed_won",
            "closed lost": "closed_lost",
        }
        k = mapped.get(s, "new")
        pipeline[k] += 1

    if crm_leads:
        pipeline["total"] = len(crm_leads)

    return jsonify(pipeline)


@app.route("/api/outreach")
def api_outreach():
    leads = get_qualified_leads()
    outreach_crm = get_sheets_data("Outreach Tracker")
    outreach_map = {}
    if outreach_crm:
        outreach_map = {
            o.get("Business Name", "").strip().lower(): o for o in outreach_crm
        }

    today = date.today()
    result = []
    for lead in leads:
        bname = lead.get("business_name", "").strip()
        entry = {
            "business_name": bname,
            "email": lead.get("email", ""),
            "phone": lead.get("phone", ""),
            "score": int(lead.get("score", 0) or 0),
            "platform": lead.get("platform", ""),
            "email_1_sent": False,
            "email_1_date": "",
            "email_2_sent": False,
            "email_2_date": "",
            "email_3_sent": False,
            "email_3_date": "",
            "reply_received": False,
            "reply_date": "",
            "meeting_booked": False,
            "meeting_date": "",
            "next_action": "Send Email 1",
            "next_action_date": today.isoformat(),
        }

        crm = outreach_map.get(bname.lower(), {})
        if crm:
            for n in (1, 2, 3):
                entry[f"email_{n}_sent"] = (
                    crm.get(f"Email {n} Sent", "").strip().lower() == "yes"
                )
                entry[f"email_{n}_date"] = crm.get(f"Email {n} Date", "")
            entry["reply_received"] = (
                crm.get("Reply Received", "").strip().lower() == "yes"
            )
            entry["reply_date"] = crm.get("Reply Date", "")
            entry["meeting_booked"] = (
                crm.get("Meeting Booked", "").strip().lower() == "yes"
            )
            entry["meeting_date"] = crm.get("Meeting Date", "")

            # Determine next action
            if entry["reply_received"] or entry["meeting_booked"]:
                entry["next_action"] = (
                    "Replied ✓" if entry["reply_received"] else "Meeting Booked ✓"
                )
                entry["next_action_date"] = ""
            elif entry["email_3_sent"]:
                entry["next_action"] = "Sequence Complete"
                entry["next_action_date"] = ""
            elif entry["email_2_sent"]:
                entry["next_action"] = "Send Email 3"
                if entry["email_2_date"]:
                    try:
                        d = datetime.strptime(entry["email_2_date"], "%Y-%m-%d").date()
                        entry["next_action_date"] = (d + timedelta(days=6)).isoformat()
                    except ValueError:
                        pass
            elif entry["email_1_sent"]:
                entry["next_action"] = "Send Email 2"
                if entry["email_1_date"]:
                    try:
                        d = datetime.strptime(entry["email_1_date"], "%Y-%m-%d").date()
                        entry["next_action_date"] = (d + timedelta(days=4)).isoformat()
                    except ValueError:
                        pass

        result.append(entry)

    return jsonify({"outreach": result})


@app.route("/api/stats")
def api_stats():
    leads = get_qualified_leads()
    outreach_crm = get_sheets_data("Outreach Tracker")

    stats = {
        "total_leads": len(leads),
        "emails_sent_total": 0,
        "emails_sent_today": 0,
        "emails_sent_week": 0,
        "replies": 0,
        "meetings": 0,
        "reply_rate": 0,
        "meeting_rate": 0,
        "conversion_rate": 0,
    }

    if outreach_crm:
        today = date.today()
        week_ago = today - timedelta(days=7)
        contacted = 0

        for row in outreach_crm:
            e1 = row.get("Email 1 Sent", "").strip().lower() == "yes"
            if e1:
                contacted += 1
            for n in (1, 2, 3):
                if row.get(f"Email {n} Sent", "").strip().lower() == "yes":
                    stats["emails_sent_total"] += 1
                    d_str = row.get(f"Email {n} Date", "")
                    if d_str:
                        try:
                            d = datetime.strptime(d_str, "%Y-%m-%d").date()
                            if d == today:
                                stats["emails_sent_today"] += 1
                            if d >= week_ago:
                                stats["emails_sent_week"] += 1
                        except ValueError:
                            pass
            if row.get("Reply Received", "").strip().lower() == "yes":
                stats["replies"] += 1
            if row.get("Meeting Booked", "").strip().lower() == "yes":
                stats["meetings"] += 1

        if contacted > 0:
            stats["reply_rate"] = round(stats["replies"] / contacted * 100, 1)
            stats["meeting_rate"] = round(stats["meetings"] / contacted * 100, 1)

        crm_leads = get_sheets_data("Leads")
        if crm_leads:
            won = sum(
                1
                for l in crm_leads
                if l.get("Status", "").strip().lower() == "closed won"
            )
            if len(crm_leads) > 0:
                stats["conversion_rate"] = round(won / len(crm_leads) * 100, 1)

    # Load services config for revenue context
    config = load_config()
    services = config.get("services", [])
    stats["services"] = [
        {"name": s.get("name_vi", s.get("name", "")), "price": s.get("price_vnd", 0)}
        for s in services
    ]

    return jsonify(stats)


@app.route("/api/email-preview", methods=["POST"])
def api_email_preview():
    data = request.json or {}
    lead_email = data.get("lead_email", "")
    seq = int(data.get("sequence_num", 1))
    lang = data.get("lang", "vi")

    leads = get_qualified_leads()
    lead = next(
        (
            l
            for l in leads
            if l.get("email", "").strip().lower() == lead_email.strip().lower()
        ),
        None,
    )
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    tpl_file = TEMPLATES_DIR / f"email_{seq}_{'cold' if seq == 1 else 'followup' if seq == 2 else 'breakup'}_{lang}.md"
    if not tpl_file.exists():
        return jsonify({"error": f"Template not found: {tpl_file.name}"}), 404

    content = tpl_file.read_text(encoding="utf-8")
    subject = f"Email {seq}"
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                subject = fm.get("subject", subject)
            except yaml.YAMLError:
                pass
            body = parts[2].strip()

    env = load_env()
    config = load_config()
    oc = config.get("outreach", {})
    variables = {
        "business_name": lead.get("business_name", ""),
        "contact_name": lead.get("contact_name", "") or lead.get("business_name", ""),
        "platform": (lead.get("platform", "") or "Shopee/TikTok Shop")
        .replace("_", " ")
        .title(),
        "monthly_orders": lead.get("monthly_orders", "500") or "500",
        "sender_name": env.get("SENDER_NAME", "") or oc.get("sender_name", ""),
        "sender_email": env.get("SENDER_EMAIL", "") or oc.get("sender_email", ""),
        "sender_zalo": env.get("SENDER_ZALO", ""),
    }
    for key, val in variables.items():
        placeholder = "{{" + key + "}}"
        subject = subject.replace(placeholder, str(val))
        body = body.replace(placeholder, str(val))

    return jsonify({"to": lead.get("email", ""), "subject": subject, "body": body, "lead": lead})


# ---------------------------------------------------------------------------
# Routes — Actions
# ---------------------------------------------------------------------------

@app.route("/api/actions/scrape", methods=["POST"])
def action_scrape():
    try:
        r = subprocess.run(
            [sys.executable, str(BASE_DIR / "leads" / "scrapers" / "google_maps_leads.py")],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR),
        )
        return jsonify({"success": r.returncode == 0, "output": r.stdout, "error": r.stderr})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/actions/qualify", methods=["POST"])
def action_qualify():
    try:
        files = sorted(glob.glob(str(LEADS_DIR / "browser_scraped_*.csv")))
        if not files:
            return jsonify({"success": False, "error": "No raw leads file found"}), 404
        r = subprocess.run(
            [sys.executable, str(BASE_DIR / "leads" / "qualify_leads.py"), "--input", files[-1]],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(BASE_DIR),
        )
        return jsonify({"success": r.returncode == 0, "output": r.stdout, "error": r.stderr})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/actions/send-batch", methods=["POST"])
def action_send_batch():
    data = request.json or {}
    dry_run = data.get("dry_run", True)
    try:
        files = sorted(glob.glob(str(LEADS_DIR / "qualified_*.csv")))
        if not files:
            return jsonify({"success": False, "error": "No qualified leads file"}), 404
        cmd = [sys.executable, str(BASE_DIR / "outreach" / "send_sequence.py"), "--input", files[-1]]
        if dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(BASE_DIR))
        return jsonify({"success": r.returncode == 0, "output": r.stdout, "error": r.stderr, "dry_run": dry_run})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/actions/sync-crm", methods=["POST"])
def action_sync_crm():
    env = load_env()
    sid = env.get("SHEETS_CRM_ID", "")
    sa_path = BASE_DIR / "service_account.json"
    if not sid:
        return jsonify({"success": False, "error": "SHEETS_CRM_ID not set in .env"}), 400
    if not sa_path.exists():
        return jsonify({"success": False, "error": "service_account.json not found"}), 400
    try:
        from google.oauth2 import service_account as sa_mod
        from googleapiclient.discovery import build

        creds = sa_mod.Credentials.from_service_account_file(
            str(sa_path), scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        svc = build("sheets", "v4", credentials=creds)
        leads = get_qualified_leads()
        if not leads:
            return jsonify({"success": False, "error": "No qualified leads"}), 404

        headers = [
            "Business Name", "Contact Name", "Email", "Phone", "Platform",
            "City", "Monthly Orders (Est)", "Pain Point", "Lead Score",
            "Status", "Last Contact Date", "Deal Value (VND)", "Notes",
        ]
        values = [headers] + [
            [
                l.get("business_name", ""), l.get("contact_name", ""),
                l.get("email", ""), l.get("phone", ""), l.get("platform", ""),
                l.get("city", ""), "", "", l.get("score", ""),
                l.get("status", "New"), "", "", l.get("notes", ""),
            ]
            for l in leads
        ]
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range="'Leads'!A1",
            valueInputOption="USER_ENTERED", body={"values": values},
        ).execute()

        o_headers = [
            "Business Name", "Email 1 Sent", "Email 1 Date",
            "Email 2 Sent", "Email 2 Date", "Email 3 Sent", "Email 3 Date",
            "Reply Received", "Reply Date", "Meeting Booked", "Meeting Date",
        ]
        o_values = [o_headers] + [
            [l.get("business_name", ""), "No", "", "No", "", "No", "", "No", "", "No", ""]
            for l in leads
        ]
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range="'Outreach Tracker'!A1",
            valueInputOption="USER_ENTERED", body={"values": o_values},
        ).execute()

        return jsonify({"success": True, "synced": len(leads), "message": f"Synced {len(leads)} leads to CRM"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
