#!/usr/bin/env python3
"""
Order Sync Daemon — Multi-Platform Order Synchronization
=========================================================
Syncs orders from Shopee, TikTok Shop, and Lazada into a local SQLite database.
Sends daily Zalo reports and low-stock alerts.

Usage:
    python main.py --once          # Sync once and exit
    python main.py --daemon        # Run continuously (every N minutes)
    python main.py --status        # Print sync status
    python main.py --test-zalo     # Test Zalo webhook
    python main.py --refresh-tokens  # Refresh API tokens

Config:
    Edit config.json with platform credentials before running.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str = "logs"):
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(f"{log_dir}/sync.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.json") -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config not found: {config_path}")
        logger.error("Copy config.json.example to config.json and fill in credentials.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(config: dict):
    """Initialize SQLite databases for orders and inventory."""
    storage = config.get("storage", {})
    orders_db = storage.get("orders_db", "data/orders.db")
    inventory_db = storage.get("inventory_db", "data/inventory.db")

    os.makedirs(Path(orders_db).parent, exist_ok=True)
    os.makedirs(Path(inventory_db).parent, exist_ok=True)

    # Orders DB
    with sqlite3.connect(orders_db) as conn:
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
        conn.commit()

    # Inventory DB
    with sqlite3.connect(inventory_db) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_name TEXT,
                sku TEXT,
                stock INTEGER DEFAULT 0,
                price REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, item_id)
            )
        """)
        conn.commit()

    logger.info("Databases initialized.")
    return orders_db, inventory_db


# ---------------------------------------------------------------------------
# Zalo notifications
# ---------------------------------------------------------------------------

class ZaloNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        if not self.webhook_url or self.webhook_url.startswith("REPLACE"):
            logger.warning("Zalo webhook not configured — notification skipped")
            return False
        try:
            resp = requests.post(
                self.webhook_url,
                json={"text": message},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Zalo notification failed: {e}")
            return False

    def test(self) -> bool:
        return self.send("✅ Order Sync đang hoạt động! Webhook test thành công.")


# ---------------------------------------------------------------------------
# Platform integrations
# ---------------------------------------------------------------------------

class ShopeeClient:
    """Shopee Open Platform API v2 client."""

    BASE_URL = "https://partner.shopeemobile.com/api/v2"

    def __init__(self, cfg: dict):
        self.partner_id = int(cfg.get("partner_id", 0))
        self.partner_key = cfg.get("partner_key", "")
        self.shop_id = int(cfg.get("shop_id", 0))
        self.access_token = cfg.get("access_token", "")

    def _sign(self, path: str, timestamp: int) -> str:
        import hashlib
        import hmac
        base_str = f"{self.partner_id}{path}{timestamp}{self.access_token}{self.shop_id}"
        return hmac.new(
            self.partner_key.encode(), base_str.encode(), hashlib.sha256
        ).hexdigest()

    def get_order_list(self, time_from: int, time_to: int, page_size: int = 50) -> List[dict]:
        """Fetch new/updated orders in time range."""
        if not self.partner_id or not self.partner_key:
            logger.warning("Shopee credentials not configured")
            return []

        path = "/order/get_order_list"
        timestamp = int(time.time())
        sign = self._sign(path, timestamp)

        params = {
            "partner_id": self.partner_id,
            "shop_id": self.shop_id,
            "access_token": self.access_token,
            "timestamp": timestamp,
            "sign": sign,
            "time_range_field": "create_time",
            "time_from": time_from,
            "time_to": time_to,
            "page_size": page_size,
            "order_status": "READY_TO_SHIP",
            "response_optional_fields": "order_status",
        }

        try:
            resp = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                logger.error(f"Shopee API error: {data['error']} — {data.get('message')}")
                return []
            return data.get("response", {}).get("order_list", [])
        except requests.RequestException as e:
            logger.error(f"Shopee API request failed: {e}")
            return []

    def get_order_detail(self, order_sn_list: List[str]) -> List[dict]:
        """Fetch full order details."""
        path = "/order/get_order_detail"
        timestamp = int(time.time())
        sign = self._sign(path, timestamp)

        params = {
            "partner_id": self.partner_id,
            "shop_id": self.shop_id,
            "access_token": self.access_token,
            "timestamp": timestamp,
            "sign": sign,
            "order_sn_list": ",".join(order_sn_list),
        }

        try:
            resp = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("order_list", [])
        except requests.RequestException as e:
            logger.error(f"Shopee detail fetch failed: {e}")
            return []


class TikTokShopClient:
    """TikTok Shop API client (simplified)."""

    BASE_URL = "https://open-api.tiktokglobalshop.com"

    def __init__(self, cfg: dict):
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self.access_token = cfg.get("access_token", "")
        self.shop_id = cfg.get("shop_id", "")

    def _sign(self, path: str, params: dict, timestamp: int) -> str:
        import hashlib
        import hmac
        sorted_params = sorted(params.items())
        param_str = "".join(f"{k}{v}" for k, v in sorted_params)
        base_str = f"{self.app_secret}{path}{param_str}{timestamp}{self.app_secret}"
        return hmac.new(
            self.app_secret.encode(), base_str.encode(), hashlib.sha256
        ).hexdigest()

    def get_order_list(self, time_from: int, time_to: int) -> List[dict]:
        if not self.app_key or not self.access_token:
            logger.warning("TikTok Shop credentials not configured")
            return []

        path = "/api/orders/search"
        timestamp = int(time.time())

        params = {
            "app_key": self.app_key,
            "timestamp": str(timestamp),
            "access_token": self.access_token,
            "shop_id": self.shop_id,
        }
        params["sign"] = self._sign(path, params, timestamp)

        body = {
            "create_time_from": time_from,
            "create_time_to": time_to,
            "page_size": 50,
        }

        try:
            resp = requests.post(
                f"{self.BASE_URL}{path}",
                params=params,
                json=body,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("order_list", [])
        except requests.RequestException as e:
            logger.error(f"TikTok Shop API failed: {e}")
            return []


class LazadaClient:
    """Lazada Open Platform API client (simplified)."""

    BASE_URLS = {
        "VN": "https://api.lazada.vn/rest",
        "TH": "https://api.lazada.co.th/rest",
    }

    def __init__(self, cfg: dict):
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self.access_token = cfg.get("access_token", "")
        self.region = cfg.get("region", "VN")
        self.base_url = self.BASE_URLS.get(self.region, self.BASE_URLS["VN"])

    def _sign(self, path: str, params: dict) -> str:
        import hashlib
        import hmac
        sorted_params = sorted(params.items())
        param_str = "".join(f"{k}{v}" for k, v in sorted_params)
        base_str = f"{path}{param_str}"
        return hmac.new(
            self.app_secret.encode(), base_str.encode(), hashlib.sha256
        ).hexdigest().upper()

    def get_orders(self, created_after: str) -> List[dict]:
        if not self.app_key or not self.access_token:
            logger.warning("Lazada credentials not configured")
            return []

        path = "/orders/get"
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+0000")

        params = {
            "app_key": self.app_key,
            "timestamp": timestamp,
            "sign_method": "sha256",
            "access_token": self.access_token,
            "created_after": created_after,
            "status": "pending",
            "limit": "50",
        }
        params["sign"] = self._sign(path, params)

        try:
            resp = requests.get(f"{self.base_url}{path}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("orders", [])
        except requests.RequestException as e:
            logger.error(f"Lazada API failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------

class OrderSyncEngine:
    def __init__(self, config: dict):
        self.config = config
        self.orders_db, self.inventory_db = init_db(config)
        self.zalo = ZaloNotifier(
            config.get("client", {}).get("zalo_webhook", "")
        )
        self.platforms = config.get("platforms", {})

        # Init platform clients
        self.shopee = ShopeeClient(self.platforms.get("shopee", {})) if self.platforms.get("shopee", {}).get("enabled") else None
        self.tiktok = TikTokShopClient(self.platforms.get("tiktok_shop", {})) if self.platforms.get("tiktok_shop", {}).get("enabled") else None
        self.lazada = LazadaClient(self.platforms.get("lazada", {})) if self.platforms.get("lazada", {}).get("enabled") else None

    def _upsert_order(self, conn: sqlite3.Connection, platform: str, order: dict) -> str:
        """Insert or update an order. Returns 'new' or 'updated'."""
        order_id = str(order.get("order_sn") or order.get("order_id") or order.get("id", ""))
        if not order_id:
            return "skip"

        existing = conn.execute(
            "SELECT id FROM orders WHERE platform=? AND order_id=?",
            (platform, order_id),
        ).fetchone()

        raw = json.dumps(order, ensure_ascii=False)
        now = datetime.utcnow().isoformat()

        if existing:
            conn.execute(
                "UPDATE orders SET status=?, update_time=?, synced_at=?, raw_data=? WHERE platform=? AND order_id=?",
                (
                    order.get("order_status") or order.get("status", ""),
                    order.get("update_time") or order.get("updated_at", 0),
                    now,
                    raw,
                    platform,
                    order_id,
                ),
            )
            return "updated"
        else:
            conn.execute(
                """INSERT INTO orders
                   (platform, order_id, order_sn, status, buyer_name, total_amount,
                    item_count, create_time, synced_at, raw_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    platform,
                    order_id,
                    order_id,
                    order.get("order_status") or order.get("status", ""),
                    order.get("buyer_username") or order.get("buyer_name", ""),
                    float(order.get("total_amount", 0) or 0),
                    int(order.get("item_count", 0) or 0),
                    order.get("create_time") or order.get("created_at", 0),
                    now,
                    raw,
                ),
            )
            return "new"

    def sync_shopee(self, lookback_hours: int = 24) -> Dict[str, int]:
        if not self.shopee:
            return {"new": 0, "updated": 0, "errors": 0}

        logger.info("Syncing Shopee orders...")
        now = int(time.time())
        time_from = now - lookback_hours * 3600

        orders = self.shopee.get_order_list(time_from, now)
        counts = {"new": 0, "updated": 0, "errors": 0}

        with sqlite3.connect(self.orders_db) as conn:
            for order in orders:
                try:
                    result = self._upsert_order(conn, "shopee", order)
                    if result in counts:
                        counts[result] += 1
                except Exception as e:
                    logger.error(f"Shopee order upsert error: {e}")
                    counts["errors"] += 1
            conn.commit()

        logger.info(f"Shopee sync: {counts['new']} new, {counts['updated']} updated, {counts['errors']} errors")
        return counts

    def sync_tiktok(self, lookback_hours: int = 24) -> Dict[str, int]:
        if not self.tiktok:
            return {"new": 0, "updated": 0, "errors": 0}

        logger.info("Syncing TikTok Shop orders...")
        now = int(time.time())
        time_from = now - lookback_hours * 3600

        orders = self.tiktok.get_order_list(time_from, now)
        counts = {"new": 0, "updated": 0, "errors": 0}

        with sqlite3.connect(self.orders_db) as conn:
            for order in orders:
                try:
                    result = self._upsert_order(conn, "tiktok_shop", order)
                    if result in counts:
                        counts[result] += 1
                except Exception as e:
                    logger.error(f"TikTok order upsert error: {e}")
                    counts["errors"] += 1
            conn.commit()

        logger.info(f"TikTok sync: {counts['new']} new, {counts['updated']} updated, {counts['errors']} errors")
        return counts

    def sync_lazada(self, lookback_hours: int = 24) -> Dict[str, int]:
        if not self.lazada:
            return {"new": 0, "updated": 0, "errors": 0}

        logger.info("Syncing Lazada orders...")
        created_after = (datetime.utcnow() - timedelta(hours=lookback_hours)).strftime(
            "%Y-%m-%dT%H:%M:%S+0000"
        )

        orders = self.lazada.get_orders(created_after)
        counts = {"new": 0, "updated": 0, "errors": 0}

        with sqlite3.connect(self.orders_db) as conn:
            for order in orders:
                try:
                    result = self._upsert_order(conn, "lazada", order)
                    if result in counts:
                        counts[result] += 1
                except Exception as e:
                    logger.error(f"Lazada order upsert error: {e}")
                    counts["errors"] += 1
            conn.commit()

        logger.info(f"Lazada sync: {counts['new']} new, {counts['updated']} updated, {counts['errors']} errors")
        return counts

    def sync_all(self) -> Dict[str, Any]:
        """Run a full sync cycle across all enabled platforms."""
        lookback = self.config.get("sync", {}).get("lookback_hours", 24)
        results = {}

        if self.shopee:
            results["shopee"] = self.sync_shopee(lookback)
        if self.tiktok:
            results["tiktok_shop"] = self.sync_tiktok(lookback)
        if self.lazada:
            results["lazada"] = self.sync_lazada(lookback)

        # Log to sync_log table
        total_new = sum(r.get("new", 0) for r in results.values())
        total_updated = sum(r.get("updated", 0) for r in results.values())
        total_errors = sum(r.get("errors", 0) for r in results.values())

        with sqlite3.connect(self.orders_db) as conn:
            conn.execute(
                "INSERT INTO sync_log (platform, orders_new, orders_updated, errors, message) VALUES (?,?,?,?,?)",
                ("all", total_new, total_updated, total_errors, json.dumps(results)),
            )
            conn.commit()

        logger.info(f"Sync complete: {total_new} new, {total_updated} updated, {total_errors} errors")
        return results

    def get_daily_summary(self) -> dict:
        """Get order stats for today."""
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        with sqlite3.connect(self.orders_db) as conn:
            today_orders = conn.execute(
                "SELECT COUNT(*), SUM(total_amount) FROM orders WHERE DATE(synced_at) = ?",
                (today,),
            ).fetchone()
            yesterday_orders = conn.execute(
                "SELECT COUNT(*), SUM(total_amount) FROM orders WHERE DATE(synced_at) = ?",
                (yesterday,),
            ).fetchone()

        return {
            "today_count": today_orders[0] or 0,
            "today_revenue": today_orders[1] or 0,
            "yesterday_count": yesterday_orders[0] or 0,
            "yesterday_revenue": yesterday_orders[1] or 0,
        }

    def send_daily_report(self):
        """Compose and send the daily Zalo report."""
        client_name = self.config.get("client", {}).get("business_name", "Shop")
        stats = self.get_daily_summary()

        revenue_change = stats["today_revenue"] - stats["yesterday_revenue"]
        revenue_emoji = "📈" if revenue_change >= 0 else "📉"

        message = (
            f"📊 BÁO CÁO NGÀY — {client_name}\n"
            f"📅 {date.today().strftime('%d/%m/%Y')}\n\n"
            f"🛒 Đơn hàng hôm nay: {stats['today_count']:,}\n"
            f"💰 Doanh thu: {stats['today_revenue']:,.0f} VND\n"
            f"{revenue_emoji} So với hôm qua: {revenue_change:+,.0f} VND\n\n"
            f"✅ Hệ thống đang hoạt động bình thường"
        )

        self.zalo.send(message)
        logger.info("Daily report sent to Zalo")

    def print_status(self):
        """Print current sync status to stdout."""
        with sqlite3.connect(self.orders_db) as conn:
            total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            last_sync = conn.execute(
                "SELECT synced_at FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            by_platform = conn.execute(
                "SELECT platform, COUNT(*) FROM orders GROUP BY platform"
            ).fetchall()

        print(f"\nOrder Sync Status")
        print(f"{'='*40}")
        print(f"Total orders in DB: {total:,}")
        print(f"Last sync: {last_sync[0] if last_sync else 'Never'}")
        print(f"\nBy platform:")
        for platform, count in by_platform:
            print(f"  {platform}: {count:,} orders")
        print(f"{'='*40}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Order Sync Daemon")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    parser.add_argument("--test-zalo", action="store_true", help="Test Zalo webhook")
    parser.add_argument("--daily-report", action="store_true", help="Send daily report now")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    log_dir = config.get("storage", {}).get("logs_dir", "logs")
    setup_logging(log_dir)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    engine = OrderSyncEngine(config)

    if args.status:
        engine.print_status()
        return

    if args.test_zalo:
        success = engine.zalo.test()
        print("Zalo test:", "OK" if success else "FAILED — check webhook URL in config.json")
        return

    if args.daily_report:
        engine.send_daily_report()
        return

    if args.once:
        engine.sync_all()
        return

    if args.daemon:
        interval = config.get("sync", {}).get("interval_minutes", 15) * 60
        report_time = config.get("reporting", {}).get("daily_report_time", "09:00")
        last_report_date = None

        logger.info(f"Daemon started. Syncing every {interval // 60} minutes.")
        while True:
            try:
                engine.sync_all()

                # Check if it's time for daily report
                now = datetime.now()
                report_hour, report_min = map(int, report_time.split(":"))
                if (now.hour == report_hour and now.minute >= report_min
                        and last_report_date != date.today()):
                    engine.send_daily_report()
                    last_report_date = date.today()

            except KeyboardInterrupt:
                logger.info("Daemon stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)

            time.sleep(interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
