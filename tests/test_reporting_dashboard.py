"""
Tests for delivery/templates/reporting_dashboard/main.py — Report generation.
"""

import importlib.util
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_report_path = Path(__file__).resolve().parent.parent / "delivery" / "templates" / "reporting_dashboard" / "main.py"
_spec = importlib.util.spec_from_file_location("reporting_dashboard_main", str(_report_path))
report_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_module)

ReportingDashboard = report_module.ReportingDashboard
ZaloNotifier = report_module.ZaloNotifier


class TestZaloNotifierReporting:
    def test_empty_webhook(self):
        n = ZaloNotifier("")
        assert n.send("test") is False

    def test_replace_placeholder(self):
        n = ZaloNotifier("REPLACE_ME")
        assert n.send("test") is False


class TestReportingDashboard:
    @pytest.fixture
    def dashboard(self, tmp_path, orders_db):
        config = {
            "client": {"business_name": "Test Shop", "zalo_webhook": ""},
            "storage": {"orders_db": orders_db},
            "reporting": {"daily_report_time": "09:00"},
        }
        return ReportingDashboard(config, output_dir=str(tmp_path / "reports"))

    def test_init(self, dashboard):
        assert dashboard.client_name == "Test Shop"
        assert Path(dashboard.output_dir).exists()

    def test_get_orders_returns_list(self, dashboard):
        today = date.today().isoformat()
        orders = dashboard._get_orders(today, today)
        assert isinstance(orders, list)

    def test_aggregate_empty(self, dashboard):
        stats = dashboard._aggregate([])
        assert stats["total"] == 0
        assert stats["revenue"] == 0
        assert stats["by_platform"] == {}

    def test_aggregate_with_orders(self, dashboard):
        orders = [
            {"platform": "shopee", "status": "COMPLETED", "total_amount": 250000},
            {"platform": "shopee", "status": "COMPLETED", "total_amount": 300000},
            {"platform": "lazada", "status": "pending", "total_amount": 150000},
        ]
        stats = dashboard._aggregate(orders)
        assert stats["total"] == 3
        assert stats["revenue"] == 700000
        assert stats["by_platform"]["shopee"] == 2
        assert stats["by_platform"]["lazada"] == 1

    def test_daily_report_returns_string(self, dashboard):
        msg = dashboard.daily_report()
        assert isinstance(msg, str)
        assert "Test Shop" in msg
        assert "BÁO CÁO NGÀY" in msg

    def test_weekly_report_generates_html(self, dashboard):
        filepath = dashboard.weekly_report()
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "Test Shop" in content
        assert "<html" in content

    def test_monthly_report_generates_html(self, dashboard):
        filepath = dashboard.monthly_report()
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "Test Shop" in content
        assert "<html" in content

    def test_monthly_report_specific_month(self, dashboard):
        filepath = dashboard.monthly_report(year=2026, month=1)
        assert Path(filepath).exists()
        assert "2026-01" in filepath

    def test_daily_report_with_comparison(self, dashboard):
        msg = dashboard.daily_report(report_date=date.today())
        assert "so hôm qua" in msg

    def test_weekly_report_covers_7_days(self, dashboard):
        today = date.today()
        filepath = dashboard.weekly_report(end_date=today)
        content = Path(filepath).read_text()
        start = today - timedelta(days=6)
        assert start.strftime("%d/%m/%Y") in content
