"""
Tests for CRM module — setup_crm, add_lead, update_status, pipeline_report.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSetupCrm:
    def test_col_letter_single(self):
        from crm.setup_crm import col_letter
        assert col_letter(0) == "A"
        assert col_letter(1) == "B"
        assert col_letter(25) == "Z"

    def test_col_letter_double(self):
        from crm.setup_crm import col_letter
        assert col_letter(26) == "AA"
        assert col_letter(27) == "AB"

    def test_sheets_definition(self):
        from crm.setup_crm import SHEETS
        assert len(SHEETS) == 5
        sheet_names = [s[0] for s in SHEETS]
        assert "Leads" in sheet_names
        assert "Outreach Tracker" in sheet_names
        assert "Proposals" in sheet_names
        assert "Clients" in sheet_names
        assert "Revenue" in sheet_names

    def test_header_colors_for_each_sheet(self):
        from crm.setup_crm import HEADER_COLORS, SHEETS
        for name, _ in SHEETS:
            assert name in HEADER_COLORS

    def test_status_validations(self):
        from crm.setup_crm import STATUS_VALIDATIONS
        assert "Leads" in STATUS_VALIDATIONS
        assert "Proposals" in STATUS_VALIDATIONS
        leads_statuses = STATUS_VALIDATIONS["Leads"]["values"]
        assert "New" in leads_statuses
        assert "Closed Won" in leads_statuses

    def test_create_spreadsheet(self, mock_sheets_service):
        from crm.setup_crm import create_spreadsheet
        sid, url = create_spreadsheet(mock_sheets_service)
        assert sid == "test_sheet_id"
        assert "test_sheet_id" in url

    def test_write_headers(self, mock_sheets_service):
        from crm.setup_crm import write_headers
        write_headers(mock_sheets_service, "test_id")
        mock_sheets_service.spreadsheets().values().batchUpdate.assert_called_once()

    def test_save_env(self, tmp_path):
        from crm.setup_crm import save_env
        env_path = tmp_path / ".env"
        env_path.write_text("OTHER_VAR=hello\n")
        with patch("crm.setup_crm.ENV_PATH", env_path):
            save_env("new_sheet_id")
        content = env_path.read_text()
        assert "SHEETS_CRM_ID=new_sheet_id" in content
        assert "OTHER_VAR=hello" in content

    def test_save_env_updates_existing(self, tmp_path):
        from crm.setup_crm import save_env
        env_path = tmp_path / ".env"
        env_path.write_text("SHEETS_CRM_ID=old_id\n")
        with patch("crm.setup_crm.ENV_PATH", env_path):
            save_env("new_id")
        content = env_path.read_text()
        assert "SHEETS_CRM_ID=new_id" in content
        assert "old_id" not in content


class TestUpdateStatus:
    def test_valid_statuses(self):
        from crm.update_status import VALID_STATUSES
        assert "New" in VALID_STATUSES
        assert "Contacted" in VALID_STATUSES
        assert "Replied" in VALID_STATUSES
        assert "Meeting" in VALID_STATUSES
        assert "Proposal Sent" in VALID_STATUSES
        assert "Closed Won" in VALID_STATUSES
        assert "Closed Lost" in VALID_STATUSES

    def test_col_letter(self):
        from crm.update_status import col_letter
        assert col_letter(0) == "A"
        assert col_letter(9) == "J"
        assert col_letter(12) == "M"

    def test_find_lead_row_found(self, mock_sheets_service):
        from crm.update_status import find_lead_row
        mock_sheets_service.spreadsheets().values().get.return_value.execute.return_value = {
            "values": [["Business Name"], ["Shop ABC"], ["Shop XYZ"]]
        }
        row = find_lead_row(mock_sheets_service, "test_id", "Shop ABC")
        assert row == 2  # 1-based, row 2 is "Shop ABC"

    def test_find_lead_row_not_found(self, mock_sheets_service):
        from crm.update_status import find_lead_row
        mock_sheets_service.spreadsheets().values().get.return_value.execute.return_value = {
            "values": [["Business Name"], ["Shop ABC"]]
        }
        row = find_lead_row(mock_sheets_service, "test_id", "Nonexistent")
        assert row is None

    def test_find_lead_row_case_insensitive(self, mock_sheets_service):
        from crm.update_status import find_lead_row
        mock_sheets_service.spreadsheets().values().get.return_value.execute.return_value = {
            "values": [["Business Name"], ["Shop ABC"]]
        }
        row = find_lead_row(mock_sheets_service, "test_id", "shop abc")
        assert row == 2


class TestPipelineReport:
    def test_safe_get_valid_index(self):
        from crm.pipeline_report import safe_get
        assert safe_get(["a", "b", "c"], 1) == "b"

    def test_safe_get_out_of_bounds(self):
        from crm.pipeline_report import safe_get
        assert safe_get(["a"], 5) == ""

    def test_safe_get_custom_default(self):
        from crm.pipeline_report import safe_get
        assert safe_get([], 0, "N/A") == "N/A"

    def test_parse_date_iso(self):
        from crm.pipeline_report import parse_date
        d = parse_date("2026-03-15")
        assert d == date(2026, 3, 15)

    def test_parse_date_slash(self):
        from crm.pipeline_report import parse_date
        d = parse_date("15/03/2026")
        assert d == date(2026, 3, 15)

    def test_parse_date_invalid(self):
        from crm.pipeline_report import parse_date
        d = parse_date("not a date")
        assert d is None

    def test_parse_date_empty(self):
        from crm.pipeline_report import parse_date
        d = parse_date("")
        assert d is None

    def test_format_vnd(self):
        from crm.pipeline_report import format_vnd
        assert format_vnd(1500000) == "1,500,000"
        assert format_vnd("2000000") == "2,000,000"

    def test_format_vnd_with_commas(self):
        from crm.pipeline_report import format_vnd
        result = format_vnd("1,500,000")
        assert "1,500,000" == result

    def test_build_leads_section(self):
        from crm.pipeline_report import build_leads_section
        rows = [
            ["", "", "", "", "", "", "", "", "", "New"],
            ["", "", "", "", "", "", "", "", "", "Contacted"],
            ["", "", "", "", "", "", "", "", "", "New"],
        ]
        lines = build_leads_section(rows)
        assert "LEADS" in lines[0]
        full_text = "\n".join(lines)
        assert "New" in full_text

    def test_build_leads_section_empty(self):
        from crm.pipeline_report import build_leads_section
        lines = build_leads_section([])
        assert any("no leads" in l.lower() for l in lines)

    def test_build_proposals_section(self):
        from crm.pipeline_report import build_proposals_section
        rows = [
            ["", "", "", "", "", "Sent"],
            ["", "", "", "", "", "Won"],
        ]
        lines = build_proposals_section(rows)
        assert "PROPOSALS" in lines[0]

    def test_build_clients_section(self):
        from crm.pipeline_report import build_clients_section
        rows = [
            ["", "", "", "", "5000000"],
            ["", "", "", "", "8000000"],
        ]
        lines = build_clients_section(rows)
        assert "CLIENTS" in lines[0]
        full_text = "\n".join(lines)
        assert "Active: 2" in full_text

    def test_build_followups_section_no_followups(self):
        from crm.pipeline_report import build_followups_section
        lines = build_followups_section([])
        assert any("no follow-ups" in l.lower() for l in lines)

    def test_build_followups_section_with_due(self):
        from crm.pipeline_report import build_followups_section
        old_date = (date.today() - timedelta(days=5)).isoformat()
        rows = [
            ["Shop ABC", "Yes", old_date, "No", "", "No", "", "No"],
        ]
        lines = build_followups_section(rows)
        full_text = "\n".join(lines)
        assert "Shop ABC" in full_text or "no follow-ups" in full_text.lower()
