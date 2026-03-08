#!/usr/bin/env python3
"""
dashboard/server.py — WOVE Agency live dashboard backend.

Serves the dashboard HTML and exposes a JSON API + SSE stream
so the frontend can show live data and trigger actions.

Run:
    cd ~/sea-automation-agency
    source venv/bin/activate
    python dashboard/server.py
Then open: http://localhost:7788
"""

import asyncio
import csv
import glob
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── PATHS ──────────────────────────────────────────────────────────────────
BASE      = Path(__file__).parent.parent          # ~/sea-automation-agency
DASH_DIR  = Path(__file__).parent                 # ~/sea-automation-agency/dashboard
ENV_PATH  = BASE / ".env"
CONFIG    = BASE / "config.yaml"
LEADS_DIR = BASE / "leads" / "data"

# ── APP ────────────────────────────────────────────────────────────────────
app = FastAPI(title="WOVE Dashboard API", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── SSE event bus (in-memory, single-user) ─────────────────────────────────
_sse_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

def push_event(event: str, data: dict):
    try:
        _sse_queue.put_nowait({"event": event, "data": data})
    except asyncio.QueueFull:
        pass


# ── HELPERS ────────────────────────────────────────────────────────────────

def load_env() -> dict:
    return dotenv_values(str(ENV_PATH)) if ENV_PATH.exists() else {}


def load_config() -> dict:
    if CONFIG.exists():
        with open(CONFIG) as f:
            return yaml.safe_load(f) or {}
    return {}


def read_all_leads() -> list[dict]:
    leads = []
    for path in sorted(LEADS_DIR.glob("*.csv")):
        try:
            with open(path) as f:
                rows = list(csv.DictReader(f))
                for r in rows:
                    r["_source_file"] = path.name
                leads.extend(rows)
        except Exception:
            pass
    return leads


def get_pipeline_stats(leads: list[dict]) -> dict:
    statuses: dict[str, int] = {}
    for r in leads:
        s = r.get("status", "new") or "new"
        statuses[s] = statuses.get(s, 0) + 1

    with_email = sum(1 for r in leads if r.get("email", "").strip())
    with_phone = sum(1 for r in leads if r.get("phone", "").strip())

    return {
        "total": len(leads),
        "new": statuses.get("new", 0),
        "contacted": statuses.get("contacted", 0) + statuses.get("Contacted", 0),
        "replied": statuses.get("replied", 0) + statuses.get("Replied", 0),
        "meeting": statuses.get("meeting", 0),
        "won": statuses.get("won", 0),
        "invalid": statuses.get("invalid_email", 0) + statuses.get("dead", 0),
        "with_email": with_email,
        "with_phone": with_phone,
    }


def get_qualified_leads() -> list[dict]:
    path = LEADS_DIR / "qualified_2026-03-04.csv"
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def get_followup_schedule(leads: list[dict]) -> list[dict]:
    """Return leads where a follow-up email is due today or overdue."""
    today = date.today()
    due: list[dict] = []
    for r in leads:
        scraped = r.get("scraped_date", "")
        status  = r.get("status", "new")
        if status not in ("contacted", "Contacted"):
            continue
        try:
            sent_date = datetime.strptime(scraped, "%Y-%m-%d").date()
        except Exception:
            continue
        days_since = (today - sent_date).days
        # Email 2: day 4, Email 3: day 10
        if 4 <= days_since < 10:
            due.append({**r, "due": "email_2", "days_since": days_since})
        elif days_since >= 10:
            due.append({**r, "due": "email_3", "days_since": days_since})
    return due


# ── API ROUTES ─────────────────────────────────────────────────────────────

@app.get("/api/pipeline")
def api_pipeline():
    leads      = read_all_leads()
    stats      = get_pipeline_stats(leads)
    qualified  = get_qualified_leads()
    followups  = get_followup_schedule(leads)
    env        = load_env()
    cfg        = load_config()

    # Follow-up dates based on first batch sent today (Mar 8)
    batch_date = date(2026, 3, 8)
    email2_due = (batch_date + timedelta(days=4)).isoformat()   # Mar 12
    email3_due = (batch_date + timedelta(days=10)).isoformat()  # Mar 18

    return {
        "as_of": datetime.now().isoformat(),
        "pipeline": stats,
        "sender": {
            "email": env.get("SENDER_EMAIL", ""),
            "name":  env.get("SENDER_NAME", ""),
        },
        "qualified_leads": [
            {
                "name":    r.get("business_name", ""),
                "email":   r.get("email", ""),
                "status":  r.get("status", "new"),
                "phone":   r.get("phone", ""),
                "score":   r.get("score", ""),
            }
            for r in qualified
        ],
        "followups_due": followups,
        "schedule": {
            "email_2_due": email2_due,
            "email_3_due": email3_due,
        },
        "revenue": {
            "mrr": 0,
            "pipeline_value": 0,
            "clients": 0,
        },
        "crm_id": env.get("SHEETS_CRM_ID", ""),
    }


@app.get("/api/leads")
def api_leads():
    leads = read_all_leads()
    return {
        "total": len(leads),
        "files": sorted(set(r["_source_file"] for r in leads)),
        "leads": [
            {k: v for k, v in r.items() if k != "_source_file"}
            for r in leads[-50:]  # last 50
        ],
    }


@app.post("/api/outreach/send")
async def api_send_outreach(payload: dict, background_tasks: BackgroundTasks):
    """
    Trigger an outreach batch.
    Body: { "csv": "qualified_2026-03-04.csv", "lang": "vi", "delay": 30 }
    """
    csv_name = payload.get("csv", "qualified_2026-03-04.csv")
    lang     = payload.get("lang", "vi")
    delay    = int(payload.get("delay", 30))
    csv_path = LEADS_DIR / csv_name

    if not csv_path.exists():
        return JSONResponse({"ok": False, "error": f"{csv_name} not found"}, status_code=404)

    background_tasks.add_task(_run_outreach, str(csv_path), lang, delay)
    return {"ok": True, "message": f"Batch started: {csv_name} ({lang}, {delay}s delay)"}


async def _run_outreach(csv_path: str, lang: str, delay: int):
    push_event("batch_start", {"csv": csv_path, "lang": lang})
    cmd = [
        sys.executable, str(BASE / "outreach" / "send_sequence.py"),
        "--input", csv_path,
        "--lang", lang,
        "--delay", str(delay),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(BASE),
        env={**os.environ, "PYTHONPATH": str(BASE)},
    )
    async for raw in proc.stdout:
        line = raw.decode().strip()
        if "[INFO]" in line or "[WARNING]" in line or "[ERROR]" in line:
            push_event("batch_log", {"line": line})
    await proc.wait()
    push_event("batch_done", {"exit_code": proc.returncode})


@app.post("/api/leads/scrape")
async def api_scrape(payload: dict, background_tasks: BackgroundTasks):
    """Trigger the Google Maps scraper."""
    query    = payload.get("query", "shop thoi trang Ho Chi Minh")
    max_res  = int(payload.get("max_results", 30))

    background_tasks.add_task(_run_scraper, query, max_res)
    return {"ok": True, "message": f"Scraper started for: {query}"}


async def _run_scraper(query: str, max_results: int):
    push_event("scrape_start", {"query": query})
    cmd = [
        sys.executable, str(BASE / "leads" / "scrapers" / "google_maps_leads.py"),
        "--query", query, "--max-results", str(max_results),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=str(BASE),
    )
    async for raw in proc.stdout:
        line = raw.decode().strip()
        if line:
            push_event("scrape_log", {"line": line})
    await proc.wait()
    push_event("scrape_done", {"exit_code": proc.returncode})


@app.get("/api/events")
async def api_events():
    """Server-Sent Events stream for live updates."""
    async def generator() -> AsyncGenerator[str, None]:
        yield "data: {\"event\":\"connected\"}\n\n"
        while True:
            try:
                item = await asyncio.wait_for(_sse_queue.get(), timeout=25.0)
                payload = json.dumps({"event": item["event"], **item["data"]})
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"event\":\"ping\"}\n\n"  # keepalive

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── SERVE DASHBOARD HTML ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = DASH_DIR / "index.html"
    return html_path.read_text()


# ── MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("WOVE Dashboard → http://localhost:7788")
    uvicorn.run(app, host="0.0.0.0", port=7788, log_level="warning")
