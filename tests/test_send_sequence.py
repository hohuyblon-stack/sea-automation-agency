"""
Tests for outreach/send_sequence.py — Email sequence logic.

We import only the pure-logic functions to avoid needing Google API auth at import time.
"""

import importlib
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The send_sequence module imports google.auth at module level, which can fail
# in environments without cryptography. We mock the problematic imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pre-mock Google modules to prevent import errors
_mock_modules = {
    "google.auth.transport.requests": MagicMock(),
    "google.oauth2.credentials": MagicMock(),
    "google_auth_oauthlib.flow": MagicMock(),
    "googleapiclient.discovery": MagicMock(),
    "googleapiclient.errors": MagicMock(),
}
for mod_name, mock in _mock_modules.items():
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock

from outreach.send_sequence import (
    SEQUENCE,
    build_template_vars,
    create_message,
    determine_next_email,
    render_template,
)


class TestDetermineNextEmail:
    def test_no_crm_data_returns_1(self):
        # Empty dict: "Email 1 Sent" defaults to not "yes", so returns 1
        assert determine_next_email({}) == 1

    def test_email1_not_sent_returns_1(self):
        crm = {
            "Email 1 Sent": "No",
            "Email 2 Sent": "No",
            "Email 3 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) == 1

    def test_email1_sent_and_4_days_passed_returns_2(self):
        sent_date = (date.today() - timedelta(days=5)).isoformat()
        crm = {
            "Email 1 Sent": "Yes",
            "Email 1 Date": sent_date,
            "Email 2 Sent": "No",
            "Email 3 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) == 2

    def test_email1_sent_too_early_for_2(self):
        sent_date = (date.today() - timedelta(days=2)).isoformat()
        crm = {
            "Email 1 Sent": "Yes",
            "Email 1 Date": sent_date,
            "Email 2 Sent": "No",
            "Email 3 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) is None

    def test_email2_sent_and_6_days_passed_returns_3(self):
        email2_date = (date.today() - timedelta(days=7)).isoformat()
        crm = {
            "Email 1 Sent": "Yes",
            "Email 1 Date": (date.today() - timedelta(days=12)).isoformat(),
            "Email 2 Sent": "Yes",
            "Email 2 Date": email2_date,
            "Email 3 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) == 3

    def test_email2_sent_too_early_for_3(self):
        email2_date = (date.today() - timedelta(days=3)).isoformat()
        crm = {
            "Email 1 Sent": "Yes",
            "Email 1 Date": (date.today() - timedelta(days=8)).isoformat(),
            "Email 2 Sent": "Yes",
            "Email 2 Date": email2_date,
            "Email 3 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) is None

    def test_all_emails_sent_returns_none(self):
        crm = {
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "Yes",
            "Email 3 Sent": "Yes",
            "Reply Received": "No",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) is None

    def test_reply_received_stops_sequence(self):
        crm = {
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "No",
            "Reply Received": "Yes",
            "Meeting Booked": "No",
        }
        assert determine_next_email(crm) is None

    def test_meeting_booked_stops_sequence(self):
        crm = {
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "No",
            "Reply Received": "No",
            "Meeting Booked": "Yes",
        }
        assert determine_next_email(crm) is None

    def test_reply_and_meeting_both_stop(self):
        crm = {
            "Email 1 Sent": "No",
            "Reply Received": "Yes",
            "Meeting Booked": "Yes",
        }
        assert determine_next_email(crm) is None


class TestRenderTemplate:
    def test_basic_rendering(self):
        template = {"subject": "Hello {{name}}", "body": "Dear {{name}}, welcome!"}
        result = render_template(template, {"name": "Shop ABC"})
        assert result["subject"] == "Hello Shop ABC"
        assert result["body"] == "Dear Shop ABC, welcome!"

    def test_multiple_variables(self):
        template = {
            "subject": "{{business_name}} - Proposal",
            "body": "Hi {{contact_name}}, your platform is {{platform}}",
        }
        result = render_template(template, {
            "business_name": "Shop XYZ",
            "contact_name": "Nguyen A",
            "platform": "Shopee",
        })
        assert "Shop XYZ" in result["subject"]
        assert "Nguyen A" in result["body"]
        assert "Shopee" in result["body"]

    def test_missing_variable_left_as_placeholder(self):
        template = {"subject": "Hi {{name}}", "body": "{{missing_var}}"}
        result = render_template(template, {"name": "Test"})
        assert "{{missing_var}}" in result["body"]


class TestBuildTemplateVars:
    def test_builds_correct_vars(self, sample_config, sample_env):
        lead = {
            "business_name": "Shop ABC",
            "contact_name": "Nguyen A",
            "platform": "shopee",
            "monthly_orders": "800",
        }
        vars = build_template_vars(lead, sample_config, sample_env)
        assert vars["business_name"] == "Shop ABC"
        assert vars["contact_name"] == "Nguyen A"
        assert vars["sender_name"] == "Test Sender"
        assert vars["sender_email"] == "test@example.com"

    def test_fallback_contact_name_to_business(self, sample_config, sample_env):
        lead = {"business_name": "Shop ABC", "contact_name": "", "platform": "", "monthly_orders": ""}
        vars = build_template_vars(lead, sample_config, sample_env)
        assert vars["contact_name"] == "Shop ABC"

    def test_platform_formatting(self, sample_config, sample_env):
        lead = {"business_name": "", "contact_name": "", "platform": "tiktok_shop", "monthly_orders": ""}
        vars = build_template_vars(lead, sample_config, sample_env)
        assert "Tiktok Shop" in vars["platform"]


class TestCreateMessage:
    def test_creates_valid_message(self):
        msg = create_message(
            to="recipient@test.com",
            subject="Test Subject",
            body="Test body content",
            sender="sender@test.com",
        )
        assert "raw" in msg
        assert len(msg["raw"]) > 0

    def test_message_contains_raw(self):
        msg = create_message(
            to="recipient@test.com",
            subject="Test",
            body="Line 1\nLine 2",
            sender="sender@test.com",
        )
        assert "raw" in msg


class TestSequenceConfig:
    def test_sequence_has_3_emails(self):
        assert len(SEQUENCE) == 3

    def test_sequence_order(self):
        assert SEQUENCE[0][0] == 1
        assert SEQUENCE[1][0] == 2
        assert SEQUENCE[2][0] == 3

    def test_sequence_timing(self):
        assert SEQUENCE[0][2] == 0
        assert SEQUENCE[1][2] == 4
        assert SEQUENCE[2][2] == 10
