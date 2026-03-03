#!/usr/bin/env python3
"""
Automated Reporting Dashboard
===============================
Generates daily, weekly, and monthly HTML/text reports from order data.
Sends summaries to Zalo and optionally emails the full report.

Usage:
    python main.py --daily          # Generate and send daily report
    python main.py --weekly         # Generate weekly summary
    python main.py --monthly        # Generate monthly report
    python main.py --daemon         # Run on schedule (daily at 9am, weekly on Monday)
    python main.py --output-dir reports/  # Custom output directory

Config:
    Uses config.json from the same directory.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import requests

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/reports.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.json") -> dict:
    if not Path(path).exists():
        logger.error("config.json not found")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


class ZaloNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        if not self.webhook_url or self.webhook_url.startswith("REPLACE"):
            logger.warning("Zalo webhook not configured — skipping notification")
            return False
        try:
            resp = requests.post(self.webhook_url, json={"text": message}, timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Zalo send failed: {e}")
            return False


class ReportingDashboard:
    def __init__(self, config: dict, output_dir: str = "reports"):
        self.config = config
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.db_path = config.get("storage", {}).get("orders_db", "data/orders.db")
        self.client_name = config.get("client", {}).get("business_name", "Shop")
        self.zalo = ZaloNotifier(config.get("client", {}).get("zalo_webhook", ""))

    def _get_orders(self, date_from: str, date_to: str) -> list:
        """Fetch orders for a date range from the DB."""
        if not Path(self.db_path).exists():
            logger.warning(f"Orders DB not found: {self.db_path}. Run order_sync first.")
            return []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT platform, status, total_amount, item_count, synced_at
                   FROM orders
                   WHERE DATE(synced_at) BETWEEN ? AND ?
                   ORDER BY synced_at""",
                (date_from, date_to),
            ).fetchall()

        return [dict(r) for r in rows]

    def _aggregate(self, orders: list) -> dict:
        """Compute aggregate stats from a list of order dicts."""
        total = len(orders)
        revenue = sum(float(o.get("total_amount") or 0) for o in orders)

        by_platform = {}
        by_status = {}

        for o in orders:
            platform = o.get("platform", "unknown")
            status = o.get("status", "unknown")
            by_platform[platform] = by_platform.get(platform, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total": total,
            "revenue": revenue,
            "by_platform": by_platform,
            "by_status": by_status,
        }

    # ------------------------------------------------------------------
    # Daily report
    # ------------------------------------------------------------------

    def daily_report(self, report_date: date = None) -> str:
        """Generate daily report. Returns Zalo message text."""
        if report_date is None:
            report_date = date.today()

        yesterday = report_date - timedelta(days=1)
        today_str = report_date.isoformat()
        yesterday_str = yesterday.isoformat()

        today_orders = self._get_orders(today_str, today_str)
        yesterday_orders = self._get_orders(yesterday_str, yesterday_str)

        today_stats = self._aggregate(today_orders)
        yesterday_stats = self._aggregate(yesterday_orders)

        order_diff = today_stats["total"] - yesterday_stats["total"]
        revenue_diff = today_stats["revenue"] - yesterday_stats["revenue"]

        order_emoji = "📈" if order_diff >= 0 else "📉"
        revenue_emoji = "📈" if revenue_diff >= 0 else "📉"

        platform_lines = "\n".join(
            f"  • {p.replace('_', ' ').title()}: {c} đơn"
            for p, c in today_stats["by_platform"].items()
        ) or "  • Chưa có dữ liệu"

        message = (
            f"📊 BÁO CÁO NGÀY — {self.client_name}\n"
            f"📅 {report_date.strftime('%d/%m/%Y')}\n\n"
            f"🛒 Tổng đơn: {today_stats['total']:,} {order_emoji} ({order_diff:+,} so hôm qua)\n"
            f"💰 Doanh thu: {today_stats['revenue']:,.0f} VND {revenue_emoji} ({revenue_diff:+,.0f})\n\n"
            f"Theo sàn:\n{platform_lines}\n\n"
            f"✅ Hệ thống đang hoạt động bình thường"
        )

        logger.info(f"Daily report generated: {today_stats['total']} orders, {today_stats['revenue']:,.0f} VND")
        return message

    # ------------------------------------------------------------------
    # Weekly report (HTML)
    # ------------------------------------------------------------------

    def weekly_report(self, end_date: date = None) -> str:
        """Generate weekly HTML report. Returns path to saved HTML file."""
        if end_date is None:
            end_date = date.today()
        start_date = end_date - timedelta(days=6)

        orders = self._get_orders(start_date.isoformat(), end_date.isoformat())
        stats = self._aggregate(orders)

        # Daily breakdown
        daily = {}
        for o in orders:
            day = o.get("synced_at", "")[:10]
            if day:
                daily[day] = daily.get(day, {"count": 0, "revenue": 0})
                daily[day]["count"] += 1
                daily[day]["revenue"] += float(o.get("total_amount") or 0)

        # Build HTML
        daily_rows = ""
        for d in sorted(daily.keys()):
            s = daily[d]
            daily_rows += f"""
            <tr>
                <td>{d}</td>
                <td>{s['count']:,}</td>
                <td>{s['revenue']:,.0f}</td>
            </tr>"""

        platform_rows = "".join(
            f"<tr><td>{p.replace('_', ' ').title()}</td><td>{c}</td></tr>"
            for p, c in stats["by_platform"].items()
        )

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Weekly Report — {self.client_name}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; max-width: 900px; margin: 40px auto; color: #333; }}
  h1 {{ color: #1a237e; }} h2 {{ color: #283593; margin-top: 2em; }}
  .metric {{ display: inline-block; background: #e8eaf6; border-radius: 8px; padding: 16px 24px; margin: 8px; text-align: center; }}
  .metric .value {{ font-size: 2em; font-weight: bold; color: #1a237e; }}
  .metric .label {{ font-size: 0.9em; color: #666; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #1a237e; color: white; padding: 10px; text-align: left; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #f5f5f5; }}
</style>
</head>
<body>
<h1>📊 Báo Cáo Tuần — {self.client_name}</h1>
<p>{start_date.strftime('%d/%m/%Y')} – {end_date.strftime('%d/%m/%Y')}</p>

<div class="metrics">
  <div class="metric"><div class="value">{stats['total']:,}</div><div class="label">Tổng đơn hàng</div></div>
  <div class="metric"><div class="value">{stats['revenue']:,.0f}</div><div class="label">Doanh thu (VND)</div></div>
  <div class="metric"><div class="value">{stats['revenue'] / max(stats['total'], 1):,.0f}</div><div class="label">Giá trị TB/đơn</div></div>
</div>

<h2>Chi Tiết Theo Ngày</h2>
<table>
  <tr><th>Ngày</th><th>Đơn hàng</th><th>Doanh thu (VND)</th></tr>
  {daily_rows or '<tr><td colspan="3">Chưa có dữ liệu</td></tr>'}
</table>

<h2>Theo Sàn</h2>
<table>
  <tr><th>Sàn</th><th>Số đơn</th></tr>
  {platform_rows or '<tr><td colspan="2">Chưa có dữ liệu</td></tr>'}
</table>

<p style="color:#999;font-size:0.85em;margin-top:3em">
  Generated by SEA Automation Agency | {datetime.now().strftime('%Y-%m-%d %H:%M')}
</p>
</body>
</html>"""

        filename = f"weekly_{start_date.isoformat()}_{end_date.isoformat()}.html"
        filepath = os.path.join(self.output_dir, filename)
        Path(filepath).write_text(html, encoding="utf-8")
        logger.info(f"Weekly report saved: {filepath}")

        # Send Zalo summary
        zalo_msg = (
            f"📊 BÁO CÁO TUẦN — {self.client_name}\n"
            f"📅 {start_date.strftime('%d/%m')}–{end_date.strftime('%d/%m/%Y')}\n\n"
            f"🛒 Tổng đơn: {stats['total']:,}\n"
            f"💰 Doanh thu: {stats['revenue']:,.0f} VND\n"
            f"📦 TB/đơn: {stats['revenue'] / max(stats['total'], 1):,.0f} VND\n\n"
            f"Xem báo cáo đầy đủ tại: {filepath}"
        )
        self.zalo.send(zalo_msg)

        return filepath

    # ------------------------------------------------------------------
    # Monthly report (HTML)
    # ------------------------------------------------------------------

    def monthly_report(self, year: int = None, month: int = None) -> str:
        """Generate monthly HTML report. Returns path to saved file."""
        today = date.today()
        year = year or today.year
        month = month or today.month

        from calendar import monthrange
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        orders = self._get_orders(start_date.isoformat(), end_date.isoformat())
        stats = self._aggregate(orders)

        # Previous month for comparison
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        _, prev_last = monthrange(prev_year, prev_month)
        prev_orders = self._get_orders(
            date(prev_year, prev_month, 1).isoformat(),
            date(prev_year, prev_month, prev_last).isoformat(),
        )
        prev_stats = self._aggregate(prev_orders)

        order_growth = (
            ((stats["total"] - prev_stats["total"]) / max(prev_stats["total"], 1)) * 100
            if prev_stats["total"] else 0
        )
        revenue_growth = (
            ((stats["revenue"] - prev_stats["revenue"]) / max(prev_stats["revenue"], 1)) * 100
            if prev_stats["revenue"] else 0
        )

        platform_rows = "".join(
            f"<tr><td>{p.replace('_', ' ').title()}</td><td>{c}</td><td>{c / max(stats['total'], 1) * 100:.1f}%</td></tr>"
            for p, c in stats["by_platform"].items()
        )

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Monthly Report — {self.client_name}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; max-width: 900px; margin: 40px auto; color: #333; line-height: 1.6; }}
  h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 8px; }}
  h2 {{ color: #283593; margin-top: 2em; }}
  .metric-grid {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 1.5em 0; }}
  .metric {{ flex: 1; min-width: 150px; background: #e8eaf6; border-radius: 8px; padding: 20px; text-align: center; }}
  .metric .value {{ font-size: 1.8em; font-weight: bold; color: #1a237e; }}
  .metric .label {{ font-size: 0.85em; color: #666; margin-top: 4px; }}
  .metric .change {{ font-size: 0.8em; margin-top: 8px; }}
  .positive {{ color: #2e7d32; }} .negative {{ color: #c62828; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th {{ background: #1a237e; color: white; padding: 10px; text-align: left; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
  .footer {{ margin-top: 3em; color: #999; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>📊 Báo Cáo Tháng {month}/{year} — {self.client_name}</h1>

<div class="metric-grid">
  <div class="metric">
    <div class="value">{stats['total']:,}</div>
    <div class="label">Tổng đơn hàng</div>
    <div class="change {'positive' if order_growth >= 0 else 'negative'}">
      {order_growth:+.1f}% so tháng trước
    </div>
  </div>
  <div class="metric">
    <div class="value">{stats['revenue'] / 1_000_000:.1f}M</div>
    <div class="label">Doanh thu (VND)</div>
    <div class="change {'positive' if revenue_growth >= 0 else 'negative'}">
      {revenue_growth:+.1f}% so tháng trước
    </div>
  </div>
  <div class="metric">
    <div class="value">{stats['revenue'] / max(stats['total'], 1) / 1000:.0f}K</div>
    <div class="label">Giá trị TB/đơn (VND)</div>
  </div>
</div>

<h2>Phân Tích Theo Sàn</h2>
<table>
  <tr><th>Sàn</th><th>Đơn hàng</th><th>Tỉ lệ</th></tr>
  {platform_rows or '<tr><td colspan="3">Chưa có dữ liệu</td></tr>'}
</table>

<h2>Khuyến Nghị</h2>
<ul>
  {'<li>Tháng này doanh thu <strong>tăng ' + f'{revenue_growth:.1f}%</strong> — tiếp tục duy trì!</li>' if revenue_growth > 0 else '<li>Doanh thu <strong>giảm ' + f'{abs(revenue_growth):.1f}%</strong> — cần xem xét chiến lược marketing</li>'}
  <li>Đồng bộ đơn hàng: <strong>{stats['total']:,} đơn</strong> được xử lý tự động trong tháng</li>
  <li>Tiết kiệm ước tính: <strong>{stats['total'] * 5 // 60:,} giờ</strong> so với xử lý thủ công</li>
</ul>

<div class="footer">
  Generated by SEA Automation Agency | {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
</body>
</html>"""

        month_str = f"{year}-{month:02d}"
        filename = f"monthly_{month_str}.html"
        filepath = os.path.join(self.output_dir, filename)
        Path(filepath).write_text(html, encoding="utf-8")
        logger.info(f"Monthly report saved: {filepath}")

        # Zalo summary
        zalo_msg = (
            f"📊 BÁO CÁO THÁNG {month}/{year} — {self.client_name}\n\n"
            f"🛒 Tổng đơn: {stats['total']:,} ({order_growth:+.1f}%)\n"
            f"💰 Doanh thu: {stats['revenue']:,.0f} VND ({revenue_growth:+.1f}%)\n"
            f"⏱ Tiết kiệm: ~{stats['total'] * 5 // 60:,} giờ xử lý thủ công\n\n"
            f"Xem báo cáo đầy đủ: {filepath}"
        )
        self.zalo.send(zalo_msg)

        return filepath


def main():
    parser = argparse.ArgumentParser(description="Automated Reporting Dashboard")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--daily", action="store_true", help="Generate and send daily report")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly HTML report")
    parser.add_argument("--monthly", action="store_true", help="Generate monthly HTML report")
    parser.add_argument("--month", default="", help="Month for monthly report (YYYY-MM)")
    parser.add_argument("--daemon", action="store_true", help="Run on schedule")
    parser.add_argument("--output-dir", default="reports", help="Output directory")
    args = parser.parse_args()

    config = load_config(args.config)
    dashboard = ReportingDashboard(config, output_dir=args.output_dir)

    if args.daily:
        msg = dashboard.daily_report()
        print(msg)
        dashboard.zalo.send(msg)
        return

    if args.weekly:
        path = dashboard.weekly_report()
        print(f"Weekly report saved: {path}")
        return

    if args.monthly:
        year, month = None, None
        if args.month:
            parts = args.month.split("-")
            year, month = int(parts[0]), int(parts[1])
        path = dashboard.monthly_report(year, month)
        print(f"Monthly report saved: {path}")
        return

    if args.daemon:
        report_cfg = config.get("reporting", {})
        report_time = report_cfg.get("daily_report_time", "09:00")
        report_hour, report_min = map(int, report_time.split(":"))

        logger.info(f"Reporting daemon started. Daily report at {report_time}.")
        last_daily = None
        last_weekly = None

        while True:
            now = datetime.now()
            today = date.today()

            try:
                # Daily report
                if now.hour == report_hour and now.minute >= report_min and last_daily != today:
                    msg = dashboard.daily_report()
                    dashboard.zalo.send(msg)
                    last_daily = today

                    # Weekly on Monday
                    if today.weekday() == 0 and last_weekly != today:
                        dashboard.weekly_report()
                        last_weekly = today

            except KeyboardInterrupt:
                logger.info("Daemon stopped.")
                break
            except Exception as e:
                logger.error(f"Report generation error: {e}", exc_info=True)

            time.sleep(60)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
