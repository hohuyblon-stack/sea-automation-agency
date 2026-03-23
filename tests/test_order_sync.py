"""
Tests for delivery/templates/order_sync/main.py — Order sync engine.
"""

import importlib.util
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Use importlib to avoid sys.path collision with other main.py files
_order_sync_path = Path(__file__).resolve().parent.parent / "delivery" / "templates" / "order_sync" / "main.py"
_spec = importlib.util.spec_from_file_location("order_sync_main", str(_order_sync_path))
order_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(order_sync)

LazadaClient = order_sync.LazadaClient
OrderSyncEngine = order_sync.OrderSyncEngine
ShopeeClient = order_sync.ShopeeClient
TikTokShopClient = order_sync.TikTokShopClient
ZaloNotifier = order_sync.ZaloNotifier
init_db = order_sync.init_db
load_config = order_sync.load_config


class TestZaloNotifier:
    def test_unconfigured_webhook_returns_false(self):
        notifier = ZaloNotifier("")
        assert notifier.send("test") is False

    def test_replace_placeholder_returns_false(self):
        notifier = ZaloNotifier("REPLACE_WITH_WEBHOOK")
        assert notifier.send("test") is False

    @patch("requests.post")
    def test_successful_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        notifier = ZaloNotifier("https://zalo.webhook.test")
        assert notifier.send("test message") is True
        mock_post.assert_called_once()

    @patch("requests.post", side_effect=order_sync.requests.RequestException("Connection error"))
    def test_failed_send(self, mock_post):
        notifier = ZaloNotifier("https://zalo.webhook.test")
        assert notifier.send("test message") is False


class TestShopeeClient:
    def test_init_empty_config(self):
        client = ShopeeClient({})
        assert client.partner_id == 0
        assert client.partner_key == ""

    def test_unconfigured_returns_empty(self):
        client = ShopeeClient({})
        orders = client.get_order_list(0, 100)
        assert orders == []


class TestTikTokShopClient:
    def test_init_empty_config(self):
        client = TikTokShopClient({})
        assert client.app_key == ""

    def test_unconfigured_returns_empty(self):
        client = TikTokShopClient({})
        orders = client.get_order_list(0, 100)
        assert orders == []


class TestLazadaClient:
    def test_init_default_region(self):
        client = LazadaClient({})
        assert client.region == "VN"
        assert "lazada.vn" in client.base_url

    def test_init_custom_region(self):
        client = LazadaClient({"region": "TH"})
        assert "lazada.co.th" in client.base_url

    def test_unconfigured_returns_empty(self):
        client = LazadaClient({})
        orders = client.get_orders("2026-01-01")
        assert orders == []


class TestInitDb:
    def test_creates_tables(self, sample_order_sync_config):
        orders_db, inventory_db = init_db(sample_order_sync_config)
        assert Path(orders_db).exists()
        assert Path(inventory_db).exists()

        with sqlite3.connect(orders_db) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t[0] for t in tables]
            assert "orders" in table_names
            assert "sync_log" in table_names

    def test_idempotent(self, sample_order_sync_config):
        init_db(sample_order_sync_config)
        init_db(sample_order_sync_config)  # should not error


class TestOrderSyncEngine:
    def test_init_no_platforms(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        assert engine.shopee is None
        assert engine.tiktok is None
        assert engine.lazada is None

    def test_sync_all_no_platforms(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        results = engine.sync_all()
        assert results == {}

    def test_upsert_order_new(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        order = {
            "order_sn": "TEST001",
            "order_status": "READY_TO_SHIP",
            "buyer_username": "buyer1",
            "total_amount": 250000,
            "item_count": 2,
            "create_time": 1700000000,
        }
        with sqlite3.connect(engine.orders_db) as conn:
            result = engine._upsert_order(conn, "shopee", order)
            conn.commit()
        assert result == "new"

    def test_upsert_order_update(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        order = {
            "order_sn": "TEST001",
            "order_status": "READY_TO_SHIP",
            "buyer_username": "buyer1",
            "total_amount": 250000,
            "item_count": 2,
        }
        with sqlite3.connect(engine.orders_db) as conn:
            engine._upsert_order(conn, "shopee", order)
            conn.commit()
            order["order_status"] = "COMPLETED"
            result = engine._upsert_order(conn, "shopee", order)
            conn.commit()
        assert result == "updated"

    def test_upsert_order_skip_no_id(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        order = {"status": "pending"}
        with sqlite3.connect(engine.orders_db) as conn:
            result = engine._upsert_order(conn, "shopee", order)
        assert result == "skip"

    def test_get_daily_summary(self, sample_order_sync_config):
        engine = OrderSyncEngine(sample_order_sync_config)
        with sqlite3.connect(engine.orders_db) as conn:
            conn.execute(
                "INSERT INTO orders (platform, order_id, total_amount, synced_at) VALUES (?,?,?,?)",
                ("shopee", "T001", 100000, date.today().isoformat()),
            )
            conn.commit()
        summary = engine.get_daily_summary()
        assert summary["today_count"] >= 1
        assert summary["today_revenue"] >= 100000

    def test_print_status(self, sample_order_sync_config, capsys):
        engine = OrderSyncEngine(sample_order_sync_config)
        engine.print_status()
        captured = capsys.readouterr()
        assert "Order Sync Status" in captured.out


class TestLoadConfig:
    def test_load_missing_config(self, tmp_path):
        with pytest.raises(SystemExit):
            load_config(str(tmp_path / "nonexistent.json"))

    def test_load_valid_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"client": {"name": "test"}}))
        config = load_config(str(config_path))
        assert config["client"]["name"] == "test"
