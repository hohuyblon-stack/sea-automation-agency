"""
Shared test fixtures for SEA Automation Agency test suite.
"""

import csv
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test outputs."""
    return tmp_path


@pytest.fixture
def sample_lead_row():
    """A single raw lead row as it comes from a CSV."""
    return {
        "business_name": "Shop Thoi Trang ABC",
        "contact_name": "Nguyen Van A",
        "email": "contact@shopabc.vn",
        "phone": "0901234567",
        "zalo": "0901234567",
        "website": "https://shopabc.vn",
        "facebook": "https://facebook.com/shopabc",
        "platform": "shopee",
        "city": "ho chi minh",
        "address": "123 Nguyen Hue, Q1",
        "category": "thoi trang",
        "source": "google_maps",
        "score": "0",
        "status": "new",
        "notes": "",
        "scraped_date": "2026-03-01",
        "post_text": "",
        "post_url": "",
        "group_name": "",
    }


@pytest.fixture
def sample_leads_csv(tmp_path, sample_lead_row):
    """Create a temporary CSV file with sample leads."""
    csv_path = tmp_path / "test_leads.csv"
    fieldnames = list(sample_lead_row.keys())

    leads = [
        sample_lead_row,
        {
            **sample_lead_row,
            "business_name": "Shop My Pham XYZ",
            "email": "info@shopxyz.vn",
            "phone": "0912345678",
            "platform": "tiktok_shop",
            "city": "ha noi",
            "website": "",
        },
        {
            **sample_lead_row,
            "business_name": "test shop",
            "email": "",
            "phone": "",
            "platform": "",
            "city": "",
            "website": "",
        },
        {
            **sample_lead_row,
            "business_name": "No Contact Shop",
            "email": "",
            "phone": "",
            "platform": "lazada",
            "city": "da nang",
        },
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead)

    return str(csv_path)


@pytest.fixture
def sample_config():
    """Sample config.yaml content as a dict."""
    return {
        "agency": {"name": "SEA Automation Agency"},
        "services": [
            {
                "id": "order_sync",
                "name": "Multi-Platform Order Sync",
                "name_vi": "Đồng bộ đơn hàng đa sàn",
                "price_vnd": 15000000,
                "price_usd": 600,
                "delivery_days": 7,
            },
        ],
        "outreach": {
            "sequence_days": [1, 4, 10],
            "sender_name": "Test Sender",
            "sender_email": "test@example.com",
        },
    }


@pytest.fixture
def sample_env():
    """Sample environment variables dict."""
    return {
        "SENDER_EMAIL": "test@example.com",
        "SENDER_NAME": "Test Sender",
        "SENDER_ZALO": "0901234567",
        "SHEETS_CRM_ID": "test_spreadsheet_id",
    }


@pytest.fixture
def sample_order_sync_config(tmp_path):
    """Config dict for order sync tests."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    return {
        "client": {
            "business_name": "Test Shop",
            "zalo_webhook": "",
        },
        "platforms": {
            "shopee": {"enabled": False},
            "tiktok_shop": {"enabled": False},
            "lazada": {"enabled": False},
        },
        "storage": {
            "orders_db": str(db_dir / "orders.db"),
            "inventory_db": str(db_dir / "inventory.db"),
            "logs_dir": str(tmp_path / "logs"),
        },
        "sync": {
            "interval_minutes": 15,
            "lookback_hours": 24,
        },
        "reporting": {
            "daily_report_time": "09:00",
        },
    }


@pytest.fixture
def orders_db(tmp_path):
    """Create a temporary orders database with sample data."""
    db_path = str(tmp_path / "orders.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                order_id TEXT NOT NULL,
                order_sn TEXT,
                status TEXT,
                buyer_name TEXT,
                total_amount REAL,
                currency TEXT DEFAULT 'VND',
                item_count INTEGER,
                create_time INTEGER,
                update_time INTEGER,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT,
                UNIQUE(platform, order_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                orders_new INTEGER DEFAULT 0,
                orders_updated INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                message TEXT
            )
        """)
        # Insert sample orders
        from datetime import date
        today = date.today().isoformat()
        conn.executemany(
            "INSERT INTO orders (platform, order_id, status, buyer_name, total_amount, item_count, synced_at) VALUES (?,?,?,?,?,?,?)",
            [
                ("shopee", "SH001", "READY_TO_SHIP", "Buyer A", 250000, 2, today),
                ("shopee", "SH002", "COMPLETED", "Buyer B", 500000, 3, today),
                ("tiktok_shop", "TT001", "pending", "Buyer C", 150000, 1, today),
                ("lazada", "LZ001", "pending", "Buyer D", 350000, 2, today),
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (platform, orders_new, orders_updated, errors, message) VALUES (?,?,?,?,?)",
            ("all", 4, 0, 0, "test sync"),
        )
        conn.commit()
    return db_path


@pytest.fixture
def inventory_db(tmp_path):
    """Create a temporary inventory database with sample data."""
    db_path = str(tmp_path / "inventory.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_name TEXT,
                sku TEXT,
                stock INTEGER DEFAULT 0,
                price REAL,
                last_alert_sent TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, item_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                item_id TEXT,
                item_name TEXT,
                stock INTEGER,
                threshold INTEGER,
                alert_type TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.executemany(
            "INSERT INTO inventory (platform, item_id, item_name, sku, stock, price) VALUES (?,?,?,?,?,?)",
            [
                ("shopee", "ITEM001", "Áo thun nam", "SKU-001", 50, 199000),
                ("shopee", "ITEM002", "Quần jean nữ", "SKU-002", 5, 350000),
                ("shopee", "ITEM003", "Giày sneaker", "SKU-003", 2, 450000),
                ("shopee", "ITEM004", "Túi xách", "SKU-004", 0, 280000),
            ],
        )
        conn.commit()
    return db_path


@pytest.fixture
def mock_sheets_service():
    """Mock Google Sheets API service."""
    service = MagicMock()
    spreadsheets = MagicMock()
    values = MagicMock()

    service.spreadsheets.return_value = spreadsheets
    spreadsheets.values.return_value = values
    spreadsheets.create.return_value.execute.return_value = {
        "spreadsheetId": "test_sheet_id",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/test_sheet_id",
    }
    spreadsheets.batchUpdate.return_value.execute.return_value = {}
    values.batchUpdate.return_value.execute.return_value = {}
    values.update.return_value.execute.return_value = {}
    values.get.return_value.execute.return_value = {"values": []}

    return service


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail API service."""
    service = MagicMock()
    users = MagicMock()
    messages = MagicMock()

    service.users.return_value = users
    users.messages.return_value = messages
    messages.send.return_value.execute.return_value = {"id": "test_msg_id"}

    return service
