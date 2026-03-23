"""
Tests for delivery/templates/inventory_alerts/main.py — Inventory monitoring.
"""

import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_inv_path = Path(__file__).resolve().parent.parent / "delivery" / "templates" / "inventory_alerts" / "main.py"
_spec = importlib.util.spec_from_file_location("inventory_alerts_main", str(_inv_path))
inv_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inv_module)

InventoryMonitor = inv_module.InventoryMonitor
ZaloNotifier = inv_module.ZaloNotifier
init_db = inv_module.init_db


class TestZaloNotifierInventory:
    def test_empty_webhook(self):
        n = ZaloNotifier("")
        assert n.send("test") is False

    @patch("requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        n = ZaloNotifier("https://webhook.test")
        assert n.send("message") is True


class TestInitDb:
    def test_creates_tables(self, tmp_path):
        db_path = init_db(str(tmp_path / "inv.db"))
        with sqlite3.connect(db_path) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = [t[0] for t in tables]
            assert "inventory" in names
            assert "alert_log" in names


class TestInventoryMonitor:
    def _make_config(self, tmp_path, inventory_db):
        return {
            "client": {"business_name": "Test Shop", "zalo_webhook": ""},
            "platforms": {},
            "storage": {"inventory_db": inventory_db},
            "inventory": {"low_stock_threshold": 10, "critical_stock_threshold": 3},
        }

    def test_init(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        assert monitor.low_threshold == 10
        assert monitor.critical_threshold == 3

    def test_get_low_stock_items(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        low = monitor.get_low_stock_items()
        assert len(low) == 3
        assert all(item["stock"] <= 10 for item in low)

    def test_should_alert_first_time(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        assert monitor.should_alert("shopee", "ITEM002") is True

    def test_should_alert_after_marking(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        monitor.mark_alert_sent("shopee", "ITEM002")
        assert monitor.should_alert("shopee", "ITEM002") is False

    def test_update_db(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        items = [
            {"item_id": "NEW001", "item_name": "New Item", "sku": "S-NEW", "stock": 100, "price": 50000},
        ]
        monitor.update_db("shopee", items)
        with sqlite3.connect(inventory_db) as conn:
            row = conn.execute("SELECT stock FROM inventory WHERE item_id='NEW001'").fetchone()
        assert row[0] == 100

    def test_update_db_upsert(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        items = [
            {"item_id": "ITEM001", "item_name": "Áo thun nam", "sku": "SKU-001", "stock": 25, "price": 199000},
        ]
        monitor.update_db("shopee", items)
        with sqlite3.connect(inventory_db) as conn:
            row = conn.execute("SELECT stock FROM inventory WHERE item_id='ITEM001'").fetchone()
        assert row[0] == 25

    def test_check_and_alert_no_platforms(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        monitor.check_and_alert()

    def test_send_full_report(self, tmp_path, inventory_db):
        config = self._make_config(tmp_path, inventory_db)
        config["client"]["zalo_webhook"] = ""
        monitor = InventoryMonitor(config)
        monitor.db_path = inventory_db
        monitor.send_full_report()
