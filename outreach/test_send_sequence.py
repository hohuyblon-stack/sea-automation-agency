#!/usr/bin/env python3
"""
Unit tests for send_sequence.py — render_template, determine_next_email, build_template_vars.

Run:  python -m pytest outreach/test_send_sequence.py -v
"""

import unittest
from datetime import date, timedelta

from send_sequence import build_template_vars, determine_next_email, render_template


# ---------------------------------------------------------------------------
# render_template tests
# ---------------------------------------------------------------------------
class TestRenderTemplate(unittest.TestCase):
    """Tests for render_template(template, variables)."""

    def test_basic_substitution(self):
        tpl = {"subject": "Hello {{name}}", "body": "Welcome {{name}}!"}
        result = render_template(tpl, {"name": "Minh"})
        self.assertEqual(result["subject"], "Hello Minh")
        self.assertEqual(result["body"], "Welcome Minh!")

    def test_multiple_variables(self):
        tpl = {
            "subject": "{{business_name}} – order sync",
            "body": "Hi {{contact_name}}, your shop {{business_name}} on {{platform}}.",
        }
        variables = {
            "business_name": "Shop ABC",
            "contact_name": "Anh Minh",
            "platform": "Shopee",
        }
        result = render_template(tpl, variables)
        self.assertEqual(result["subject"], "Shop ABC – order sync")
        self.assertIn("Anh Minh", result["body"])
        self.assertIn("Shop ABC", result["body"])
        self.assertIn("Shopee", result["body"])

    def test_missing_variable_left_as_placeholder(self):
        tpl = {"subject": "Hi {{name}}", "body": "Order: {{order_id}}"}
        result = render_template(tpl, {"name": "Lan"})
        self.assertEqual(result["subject"], "Hi Lan")
        self.assertEqual(result["body"], "Order: {{order_id}}")

    def test_empty_variables_dict(self):
        tpl = {"subject": "{{a}} and {{b}}", "body": "Nothing changes"}
        result = render_template(tpl, {})
        self.assertEqual(result["subject"], "{{a}} and {{b}}")
        self.assertEqual(result["body"], "Nothing changes")

    def test_variable_appears_multiple_times(self):
        tpl = {
            "subject": "{{name}}",
            "body": "Dear {{name}}, {{name}} is great.",
        }
        result = render_template(tpl, {"name": "Huy"})
        self.assertEqual(result["body"], "Dear Huy, Huy is great.")

    def test_non_string_variable_converted(self):
        tpl = {"subject": "Orders: {{count}}", "body": "You have {{count}} orders."}
        result = render_template(tpl, {"count": 500})
        self.assertEqual(result["subject"], "Orders: 500")

    def test_original_template_not_mutated(self):
        tpl = {"subject": "Hi {{name}}", "body": "Body {{name}}"}
        render_template(tpl, {"name": "Test"})
        # Original strings should be unchanged (str.replace returns new str)
        self.assertEqual(tpl["subject"], "Hi {{name}}")


# ---------------------------------------------------------------------------
# determine_next_email tests
# ---------------------------------------------------------------------------
class TestDetermineNextEmail(unittest.TestCase):
    """Tests for determine_next_email(crm_row)."""

    def _base_row(self, **overrides):
        row = {
            "Reply Received": "No",
            "Meeting Booked": "No",
            "Email 1 Sent": "No",
            "Email 2 Sent": "No",
            "Email 3 Sent": "No",
            "Email 1 Date": "",
            "Email 2 Date": "",
            "Email 3 Date": "",
        }
        row.update(overrides)
        return row

    def test_fresh_lead_returns_1(self):
        self.assertEqual(determine_next_email(self._base_row()), 1)

    def test_email_1_sent_and_4_days_passed_returns_2(self):
        four_days_ago = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 1 Date": four_days_ago,
        })
        self.assertEqual(determine_next_email(row), 2)

    def test_email_1_sent_too_early_for_2_returns_none(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 1 Date": yesterday,
        })
        self.assertIsNone(determine_next_email(row))

    def test_email_2_sent_and_6_days_passed_returns_3(self):
        six_days_ago = (date.today() - timedelta(days=6)).strftime("%Y-%m-%d")
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "Yes",
            "Email 2 Date": six_days_ago,
        })
        self.assertEqual(determine_next_email(row), 3)

    def test_email_2_sent_too_early_for_3_returns_none(self):
        two_days_ago = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "Yes",
            "Email 2 Date": two_days_ago,
        })
        self.assertIsNone(determine_next_email(row))

    def test_all_emails_sent_returns_none(self):
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 2 Sent": "Yes",
            "Email 3 Sent": "Yes",
        })
        self.assertIsNone(determine_next_email(row))

    def test_replied_stops_sequence(self):
        row = self._base_row(**{"Reply Received": "Yes"})
        self.assertIsNone(determine_next_email(row))

    def test_meeting_booked_stops_sequence(self):
        row = self._base_row(**{"Meeting Booked": "Yes"})
        self.assertIsNone(determine_next_email(row))

    def test_replied_even_with_emails_pending(self):
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Reply Received": "Yes",
        })
        self.assertIsNone(determine_next_email(row))

    def test_email_1_sent_no_date_returns_2(self):
        """If email 1 was sent but date is missing, proceed to email 2."""
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 1 Date": "",
        })
        self.assertEqual(determine_next_email(row), 2)

    def test_case_insensitive_yes(self):
        row = self._base_row(**{"Reply Received": " YES "})
        self.assertIsNone(determine_next_email(row))

    def test_email_1_sent_exactly_on_boundary_day(self):
        """Day 4 exactly should allow email 2."""
        boundary = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
        row = self._base_row(**{
            "Email 1 Sent": "Yes",
            "Email 1 Date": boundary,
        })
        self.assertEqual(determine_next_email(row), 2)


# ---------------------------------------------------------------------------
# build_template_vars tests
# ---------------------------------------------------------------------------
class TestBuildTemplateVars(unittest.TestCase):
    """Tests for build_template_vars(lead, config, env)."""

    def _default_lead(self, **overrides):
        lead = {
            "business_name": "Shop Thoi Trang ABC",
            "contact_name": "Nguyen Van A",
            "platform": "shopee",
            "monthly_orders": "1000",
        }
        lead.update(overrides)
        return lead

    def _default_config(self):
        return {
            "outreach": {
                "sender_name": "Ho Khac Huy",
                "sender_email": "hohuyblon@gmail.com",
            }
        }

    def _default_env(self):
        return {
            "SENDER_NAME": "Huy Ho",
            "SENDER_EMAIL": "huy@agency.com",
            "SENDER_ZALO": "0901234567",
        }

    def test_all_fields_present(self):
        result = build_template_vars(
            self._default_lead(), self._default_config(), self._default_env()
        )
        self.assertEqual(result["business_name"], "Shop Thoi Trang ABC")
        self.assertEqual(result["contact_name"], "Nguyen Van A")
        self.assertEqual(result["platform"], "Shopee")  # title-cased
        self.assertEqual(result["monthly_orders"], "1000")
        self.assertEqual(result["sender_name"], "Huy Ho")  # env overrides config
        self.assertEqual(result["sender_email"], "huy@agency.com")
        self.assertEqual(result["sender_zalo"], "0901234567")

    def test_env_overrides_config_for_sender(self):
        result = build_template_vars(
            self._default_lead(), self._default_config(), self._default_env()
        )
        # Env should win over config
        self.assertEqual(result["sender_name"], "Huy Ho")
        self.assertEqual(result["sender_email"], "huy@agency.com")

    def test_config_used_when_env_missing(self):
        env = {"SENDER_ZALO": "0901234567"}  # No SENDER_NAME or SENDER_EMAIL
        result = build_template_vars(
            self._default_lead(), self._default_config(), env
        )
        self.assertEqual(result["sender_name"], "Ho Khac Huy")
        self.assertEqual(result["sender_email"], "hohuyblon@gmail.com")

    def test_missing_contact_name_defaults(self):
        lead = self._default_lead(contact_name="")
        result = build_template_vars(lead, self._default_config(), self._default_env())
        self.assertEqual(result["contact_name"], "Anh/Chị")

    def test_missing_platform_defaults(self):
        lead = self._default_lead(platform="")
        result = build_template_vars(lead, self._default_config(), self._default_env())
        self.assertEqual(result["platform"], "Shopee/TikTok Shop")

    def test_missing_monthly_orders_defaults(self):
        lead = self._default_lead(monthly_orders="")
        result = build_template_vars(lead, self._default_config(), self._default_env())
        self.assertEqual(result["monthly_orders"], "500+")

    def test_platform_underscore_replaced_and_titled(self):
        lead = self._default_lead(platform="tiktok_shop")
        result = build_template_vars(lead, self._default_config(), self._default_env())
        self.assertEqual(result["platform"], "Tiktok Shop")

    def test_empty_config_outreach_section(self):
        result = build_template_vars(
            self._default_lead(), {}, self._default_env()
        )
        # Should still work — env provides sender info
        self.assertEqual(result["sender_name"], "Huy Ho")

    def test_completely_empty_lead(self):
        result = build_template_vars({}, self._default_config(), self._default_env())
        self.assertEqual(result["business_name"], "")
        self.assertEqual(result["contact_name"], "Anh/Chị")
        self.assertEqual(result["platform"], "Shopee/TikTok Shop")
        self.assertEqual(result["monthly_orders"], "500+")


if __name__ == "__main__":
    unittest.main()
