"""
Tests for proposals/generate_proposal.py — Proposal generation.
"""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proposals.generate_proposal import (
    compute_derived_vars,
    generate_proposal,
    md_to_html,
    render_template,
)


class TestRenderTemplate:
    def test_basic_replacement(self):
        result = render_template("Hello {{name}}!", {"name": "World"})
        assert result == "Hello World!"

    def test_multiple_replacements(self):
        result = render_template("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_variable_stays(self):
        result = render_template("Hello {{name}}", {})
        assert "{{name}}" in result

    def test_numeric_value(self):
        result = render_template("Price: {{price}}", {"price": 15000000})
        assert "15000000" in result

    def test_empty_template(self):
        result = render_template("", {"key": "val"})
        assert result == ""


class TestComputeDerivedVars:
    def test_standard_computation(self):
        data = {"monthly_orders": "800", "business_name": "Shop ABC"}
        derived = compute_derived_vars(data)
        assert derived["manual_hours_per_month"] == round(800 * 5 / 60)
        assert derived["proposal_id"].startswith("SEA-")
        assert date.today().strftime("%Y%m%d") in derived["proposal_id"]
        assert "SHOPABC" in derived["proposal_id"]

    def test_default_orders(self):
        derived = compute_derived_vars({})
        assert derived["manual_hours_per_month"] == round(500 * 5 / 60)

    def test_invalid_orders_fallback(self):
        derived = compute_derived_vars({"monthly_orders": "not_a_number"})
        assert derived["manual_hours_per_month"] == round(500 * 5 / 60)

    def test_labor_cost_format(self):
        derived = compute_derived_vars({"monthly_orders": "1000", "business_name": "X"})
        # 1000 orders * 5 min / 60 = 83 hours
        # 83 * 100000 = 8,300,000
        assert "." in derived["labor_cost_saved_vnd"]  # Vietnamese number format uses dots

    def test_proposal_date_format(self):
        derived = compute_derived_vars({"business_name": "Test"})
        assert "/" in derived["proposal_date"]


class TestMdToHtml:
    def test_basic_html_output(self):
        result = md_to_html("# Hello World", title="Test")
        assert "<html" in result
        assert "Test" in result

    def test_contains_body(self):
        result = md_to_html("Some **bold** text")
        assert "<body>" in result

    def test_title_in_head(self):
        result = md_to_html("Content", title="My Proposal")
        assert "My Proposal" in result

    def test_includes_styling(self):
        result = md_to_html("Content")
        assert "<style>" in result


class TestGenerateProposal:
    @pytest.fixture
    def template_file(self, tmp_path):
        template = tmp_path / "template.md"
        template.write_text(
            "# Proposal for {{business_name}}\n\n"
            "Dear {{client_name}},\n\n"
            "Platform: {{platform}}\n"
            "Monthly orders: {{monthly_orders}}\n"
            "Price: {{price_vnd}} VND\n"
            "Proposal ID: {{proposal_id}}\n"
        )
        return str(template)

    def test_generates_md_and_html(self, template_file, tmp_path, sample_config, sample_env):
        client_data = {
            "client_name": "Nguyen A",
            "business_name": "Shop ABC",
            "platform": "Shopee",
            "monthly_orders": "800",
            "pain_point": "Manual processing",
            "service_id": "order_sync",
        }
        with patch("proposals.generate_proposal.load_config", return_value=sample_config), \
             patch("proposals.generate_proposal.load_env", return_value=sample_env):
            md_path, html_path = generate_proposal(
                template_path=template_file,
                client_data=client_data,
                output_dir=str(tmp_path / "output"),
                config=sample_config,
                env=sample_env,
            )
        assert Path(md_path).exists()
        assert Path(html_path).exists()
        md_content = Path(md_path).read_text()
        assert "Shop ABC" in md_content
        assert "Nguyen A" in md_content

    def test_html_contains_proposal_content(self, template_file, tmp_path, sample_config, sample_env):
        client_data = {"client_name": "Test", "business_name": "Test Shop", "service_id": "order_sync"}
        md_path, html_path = generate_proposal(
            template_path=template_file,
            client_data=client_data,
            output_dir=str(tmp_path / "output2"),
            config=sample_config,
            env=sample_env,
        )
        html_content = Path(html_path).read_text()
        assert "<html" in html_content
        assert "Test Shop" in html_content

    def test_missing_template_exits(self, tmp_path, sample_config, sample_env):
        with pytest.raises(SystemExit):
            generate_proposal(
                template_path="/nonexistent/template.md",
                client_data={},
                output_dir=str(tmp_path),
                config=sample_config,
                env=sample_env,
            )

    def test_output_filename_format(self, template_file, tmp_path, sample_config, sample_env):
        client_data = {"business_name": "Shop Thoi Trang A", "service_id": "order_sync"}
        md_path, html_path = generate_proposal(
            template_path=template_file,
            client_data=client_data,
            output_dir=str(tmp_path / "output3"),
            config=sample_config,
            env=sample_env,
        )
        assert "proposal_" in Path(md_path).name
        assert date.today().isoformat() in Path(md_path).name
