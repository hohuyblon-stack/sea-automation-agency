#!/usr/bin/env python3
"""
Inventory Alert System
=======================
Monitors inventory levels across Shopee, TikTok Shop, and Lazada.
Sends Zalo alerts when stock falls below configurable thresholds.

Usage:
    python main.py --once          # Check inventory once
    python main.py --daemon        # Monitor continuously
    python main.py --report        # Send full inventory report
    python main.py --test-zalo     # Test Zalo webhook

Config:
    Uses the same config.json as order_sync (or a standalone one).
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict

import requests

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/inventory.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.json") -> dict:
    if not Path(path).exists():
        logger.error(f"config.json not found at {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str = "data/inventory.db"):
    os.makedirs(Path(db_path).parent, exist_ok=True)
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
        conn.commit()
    return db_path


# ---------------------------------------------------------------------------
# Zalo
# ---------------------------------------------------------------------------

class ZaloNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        if not self.webhook_url or self.webhook_url.startswith("REPLACE"):
            logger.warning("Zalo webhook not configured")
            return False
        try:
            resp = requests.post(self.webhook_url, json={"text": message}, timeout=10)
            resp.raise_for_status()
            logger.info("Zalo alert sent")
            return True
        except requests.RequestException as e:
            logger.error(f"Zalo failed: {e}")
            return False

    def test(self) -> bool:
        return self.send("✅ Inventory Alert System đang hoạt động!")


# ---------------------------------------------------------------------------
# Shopee inventory fetcher
# ---------------------------------------------------------------------------

class ShopeeInventory:
    """Fetch product stock from Shopee Open Platform."""

    BASE_URL = "https://partner.shopeemobile.com/api/v2"

    def __init__(self, cfg: dict):
        self.partner_id = int(cfg.get("partner_id", 0))
        self.partner_key = cfg.get("partner_key", "")
        self.shop_id = int(cfg.get("shop_id", 0))
        self.access_token = cfg.get("access_token", "")

    def _sign(self, path: str, ts: int) -> str:
        import hashlib, hmac
        base = f"{self.partner_id}{path}{ts}{self.access_token}{self.shop_id}"
        return hmac.new(self.partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()

    def get_item_list(self) -> List[dict]:
        if not self.partner_id:
            return []
        path = "/product/get_item_list"
        ts = int(time.time())
        params = {
            "partner_id": self.partner_id,
            "shop_id": self.shop_id,
            "access_token": self.access_token,
            "timestamp": ts,
            "sign": self._sign(path, ts),
            "offset": 0,
            "page_size": 100,
            "item_status": "NORMAL",
        }
        try:
            resp = requests.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
            data = resp.json()
            return data.get("response", {}).get("item", [])
        except Exception as e:
            logger.error(f"Shopee inventory fetch failed: {e}")
            return []

    def get_stock(self) -> List[Dict]:
        """Return list of {item_id, item_name, stock, price}."""
        items = self.get_item_list()
        result = []
        for item in items:
            result.append({
                "item_id": str(item.get("item_id", "")),
                "item_name": item.get("item_name", ""),
                "sku": item.get("item_sku", ""),
                "stock": int(item.get("stock", 0)),
                "price": float(item.get("current_price", 0)),
            })
        return result


# ---------------------------------------------------------------------------
# Inventory monitor
# ---------------------------------------------------------------------------

class InventoryMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.db_path = init_db(config.get("storage", {}).get("inventory_db", "data/inventory.db"))
        self.zalo = ZaloNotifier(config.get("client", {}).get("zalo_webhook", ""))
        self.low_threshold = config.get("inventory", {}).get("low_stock_threshold", 10)
        self.critical_threshold = config.get("inventory", {}).get("critical_stock_threshold", 3)

        platforms = config.get("platforms", {})
        self.shopee_client = (
            ShopeeInventory(platforms["shopee"])
            if platforms.get("shopee", {}).get("enabled")
            else None
        )

    def update_db(self, platform: str, items: List[dict]):
        """Update inventory table with latest stock levels."""
        with sqlite3.connect(self.db_path) as conn:
            for item in items:
                conn.execute("""
                    INSERT INTO inventory (platform, item_id, item_name, sku, stock, price, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(platform, item_id) DO UPDATE SET
                        item_name=excluded.item_name,
                        stock=excluded.stock,
                        price=excluded.price,
                        updated_at=CURRENT_TIMESTAMP
                """, (
                    platform,
                    item["item_id"],
                    item.get("item_name", ""),
                    item.get("sku", ""),
                    item.get("stock", 0),
                    item.get("price", 0),
                ))
            conn.commit()

    def get_low_stock_items(self) -> List[dict]:
        """Return all items below low_threshold."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT platform, item_id, item_name, stock FROM inventory WHERE stock <= ? ORDER BY stock ASC",
                (self.low_threshold,),
            ).fetchall()
        return [{"platform": r[0], "item_id": r[1], "item_name": r[2], "stock": r[3]} for r in rows]

    def should_alert(self, platform: str, item_id: str) -> bool:
        """Avoid sending duplicate alerts within the same day."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_alert_sent FROM inventory WHERE platform=? AND item_id=?",
                (platform, item_id),
            ).fetchone()
        if not row or not row[0]:
            return True
        last_alert = row[0][:10]  # YYYY-MM-DD
        return last_alert != date.today().isoformat()

    def mark_alert_sent(self, platform: str, item_id: str):
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE inventory SET last_alert_sent=? WHERE platform=? AND item_id=?",
                (today, platform, item_id),
            )
            conn.commit()

    def check_and_alert(self):
        """Check inventory and send alerts for low-stock items."""
        if self.shopee_client:
            items = self.shopee_client.get_stock()
            self.update_db("shopee", items)

        low_items = self.get_low_stock_items()

        critical = [i for i in low_items if i["stock"] <= self.critical_threshold]
        warning = [i for i in low_items if self.critical_threshold < i["stock"] <= self.low_threshold]

        client_name = self.config.get("client", {}).get("business_name", "Shop")

        if critical:
            items_needing_alert = [i for i in critical if self.should_alert(i["platform"], i["item_id"])]
            if items_needing_alert:
                lines = "\n".join(
                    f"  🔴 {i['item_name']} — còn {i['stock']} cái ({i['platform']})"
                    for i in items_needing_alert[:10]
                )
                message = (
                    f"🚨 CẢNH BÁO KHẨN — {client_name}\n"
                    f"Sản phẩm sắp hết hàng:\n{lines}\n\n"
                    f"Cần nhập hàng NGAY để tránh oversell!"
                )
                self.zalo.send(message)
                for i in items_needing_alert:
                    self.mark_alert_sent(i["platform"], i["item_id"])
                logger.info(f"Critical stock alert sent for {len(items_needing_alert)} items")

        if warning:
            items_needing_alert = [i for i in warning if self.should_alert(i["platform"], i["item_id"])]
            if items_needing_alert:
                lines = "\n".join(
                    f"  ⚠️ {i['item_name']} — còn {i['stock']} cái ({i['platform']})"
                    for i in items_needing_alert[:10]
                )
                message = (
                    f"⚠️ CẢNH BÁO TỒN KHO — {client_name}\n"
                    f"Sản phẩm sắp hết (dưới {self.low_threshold} cái):\n{lines}"
                )
                self.zalo.send(message)
                for i in items_needing_alert:
                    self.mark_alert_sent(i["platform"], i["item_id"])
                logger.info(f"Low stock alert sent for {len(items_needing_alert)} items")

        if not low_items:
            logger.info("Inventory check complete — no low stock items")

    def send_full_report(self):
        """Send a full inventory summary to Zalo."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
            low = conn.execute(
                "SELECT COUNT(*) FROM inventory WHERE stock <= ?", (self.low_threshold,)
            ).fetchone()[0]
            zero = conn.execute("SELECT COUNT(*) FROM inventory WHERE stock = 0").fetchone()[0]

        client_name = self.config.get("client", {}).get("business_name", "Shop")
        message = (
            f"📦 BÁO CÁO TỒN KHO — {client_name}\n"
            f"📅 {date.today().strftime('%d/%m/%Y')}\n\n"
            f"Tổng sản phẩm: {total:,}\n"
            f"Sắp hết hàng (≤{self.low_threshold}): {low}\n"
            f"Hết hàng (= 0): {zero}\n\n"
            f"{'⚠️ Cần nhập hàng!' if low > 0 else '✅ Tồn kho ổn định'}"
        )
        self.zalo.send(message)


def main():
    parser = argparse.ArgumentParser(description="Inventory Alert System")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument("--daemon", action="store_true", help="Monitor continuously")
    parser.add_argument("--report", action="store_true", help="Send full inventory report")
    parser.add_argument("--test-zalo", action="store_true")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in minutes (daemon mode)")
    args = parser.parse_args()

    config = load_config(args.config)
    monitor = InventoryMonitor(config)

    if args.test_zalo:
        ok = monitor.zalo.test()
        print("Zalo test:", "OK" if ok else "FAILED")
        return

    if args.report:
        monitor.send_full_report()
        return

    if args.once:
        monitor.check_and_alert()
        return

    if args.daemon:
        interval = args.interval * 60
        logger.info(f"Inventory monitor started — checking every {args.interval} minutes")
        while True:
            try:
                monitor.check_and_alert()
            except KeyboardInterrupt:
                logger.info("Monitor stopped.")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
            time.sleep(interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
