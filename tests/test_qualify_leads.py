"""
Tests for leads/qualify_leads.py — Lead scoring and qualification pipeline.
"""

import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from leads.qualify_leads import (
    DEFAULT_MIN_SCORE,
    DISQUALIFY_PATTERNS,
    ECOM_PLATFORMS,
    MAJOR_CITIES,
    SELLER_KEYWORDS,
    ScoredLead,
    is_disqualified,
    load_csv,
    qualify,
    save_csv,
    score_lead,
)


class TestScoreLead:
    def test_full_score_lead(self, sample_lead_row):
        score, reason = score_lead(sample_lead_row)
        assert score > 0
        assert "has_phone" in reason
        assert "has_email" in reason
        assert "platform:shopee" in reason

    def test_phone_gives_30_points(self):
        row = {"phone": "0901234567", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 30
        assert "has_phone" in reason

    def test_email_gives_20_points(self):
        row = {"phone": "", "email": "test@shop.vn", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 20
        assert "has_email" in reason

    def test_platform_gives_20_points(self):
        row = {"phone": "", "email": "", "platform": "shopee", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 20
        assert "platform:shopee" in reason

    def test_major_city_gives_15_points(self):
        row = {"phone": "", "email": "", "platform": "", "city": "ho chi minh", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 15
        assert "major_city" in reason

    def test_website_gives_10_points(self):
        row = {"phone": "", "email": "", "platform": "", "city": "", "website": "https://shop.vn", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 10
        assert "has_website" in reason

    def test_keyword_density_scoring(self):
        row = {"phone": "", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "shop bán order freeship cod", "score": "0"}
        score, reason = score_lead(row)
        assert score > 0
        assert "keywords" in reason

    def test_max_keyword_score_is_5(self):
        all_keywords = " ".join(SELLER_KEYWORDS)
        row = {"phone": "", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": all_keywords, "score": "0"}
        score, _ = score_lead(row)
        assert score <= 5  # keyword score alone capped at 5

    def test_existing_score_bonus(self):
        row = {"phone": "", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "80"}
        score, _ = score_lead(row)
        assert score == 4  # 80 // 20 = 4, min(4, 5) = 4

    def test_score_capped_at_100(self, sample_lead_row):
        sample_lead_row["post_text"] = " ".join(SELLER_KEYWORDS)
        sample_lead_row["score"] = "100"
        score, _ = score_lead(sample_lead_row)
        assert score <= 100

    def test_empty_row(self):
        row = {"phone": "", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": ""}
        score, reason = score_lead(row)
        assert score == 0
        assert reason == ""

    def test_multiple_platforms(self):
        row = {"phone": "", "email": "", "platform": "shopee, lazada", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 20
        assert "platform:" in reason

    def test_phone_with_country_code(self):
        row = {"phone": "+84901234567", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, reason = score_lead(row)
        assert score == 30

    def test_short_phone_no_points(self):
        row = {"phone": "12345", "email": "", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, _ = score_lead(row)
        assert score == 0

    def test_email_without_at_no_points(self):
        row = {"phone": "", "email": "not_an_email", "platform": "", "city": "", "website": "", "business_name": "", "post_text": "", "score": "0"}
        score, _ = score_lead(row)
        assert score == 0


class TestIsDisqualified:
    def test_no_contact_info_disqualified(self):
        row = {"business_name": "Shop", "email": "", "phone": "", "status": "new"}
        result = is_disqualified(row)
        assert result == "no_contact_info"

    def test_test_business_name_disqualified(self):
        row = {"business_name": "test shop", "email": "a@b.com", "phone": "0901234567", "status": "new"}
        result = is_disqualified(row)
        assert "junk_name" in result

    def test_example_name_disqualified(self):
        row = {"business_name": "example store", "email": "a@b.com", "phone": "0901234567", "status": "new"}
        result = is_disqualified(row)
        assert "junk_name" in result

    def test_demo_name_disqualified(self):
        row = {"business_name": "demo biz", "email": "a@b.com", "phone": "0901234567", "status": "new"}
        result = is_disqualified(row)
        assert "junk_name" in result

    def test_test_email_disqualified(self):
        row = {"business_name": "Good Shop", "email": "test@example.com", "phone": "0901234567", "status": "new"}
        result = is_disqualified(row)
        assert "junk_email" in result

    def test_closed_lost_status_disqualified(self):
        row = {"business_name": "Shop", "email": "a@b.com", "phone": "0901234567", "status": "closed lost"}
        result = is_disqualified(row)
        assert "status:closed lost" == result

    def test_do_not_contact_disqualified(self):
        row = {"business_name": "Shop", "email": "a@b.com", "phone": "0901234567", "status": "do not contact"}
        result = is_disqualified(row)
        assert "status:" in result

    def test_valid_lead_not_disqualified(self, sample_lead_row):
        result = is_disqualified(sample_lead_row)
        assert result is None

    def test_phone_only_not_disqualified(self):
        row = {"business_name": "Good Shop", "email": "", "phone": "0901234567", "status": "new"}
        result = is_disqualified(row)
        assert result is None

    def test_email_only_not_disqualified(self):
        row = {"business_name": "Good Shop", "email": "shop@real.com", "phone": "", "status": "new"}
        result = is_disqualified(row)
        assert result is None


class TestLoadCsv:
    def test_load_existing_csv(self, sample_leads_csv):
        rows = load_csv(sample_leads_csv)
        assert len(rows) == 4
        assert rows[0]["business_name"] == "Shop Thoi Trang ABC"

    def test_load_nonexistent_csv(self):
        with pytest.raises(SystemExit):
            load_csv("/nonexistent/path.csv")


class TestSaveCsv:
    def test_save_leads(self, tmp_path):
        leads = [
            ScoredLead(
                business_name="Test Shop",
                contact_name="Test",
                email="test@shop.vn",
                phone="0901234567",
                score=75,
            ),
        ]
        output = str(tmp_path / "output.csv")
        save_csv(leads, output)
        assert Path(output).exists()

        with open(output, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["business_name"] == "Test Shop"
        assert rows[0]["score"] == "75"

    def test_save_empty_leads(self, tmp_path):
        output = str(tmp_path / "empty.csv")
        save_csv([], output)
        assert not Path(output).exists()

    def test_save_creates_directories(self, tmp_path):
        output = str(tmp_path / "nested" / "dir" / "output.csv")
        leads = [ScoredLead(business_name="Test", contact_name="", email="a@b.com", phone="0901234567", score=50)]
        save_csv(leads, output)
        assert Path(output).exists()


class TestQualifyPipeline:
    def test_qualify_filters_and_scores(self, sample_leads_csv, tmp_path):
        output = str(tmp_path / "qualified.csv")
        results = qualify(sample_leads_csv, output, min_score=30)
        # Shop ABC has phone+email+platform+major_city = 85+ points
        # Shop XYZ has phone+email+platform+major_city = 85+ points
        # test shop is disqualified (junk name pattern)
        # No Contact Shop is disqualified (no contact info)
        assert len(results) >= 1
        assert all(r.score >= 30 for r in results)

    def test_qualify_respects_min_score(self, sample_leads_csv, tmp_path):
        output = str(tmp_path / "qualified_high.csv")
        results = qualify(sample_leads_csv, output, min_score=90)
        # Higher bar should give fewer results
        high_count = len(results)

        output2 = str(tmp_path / "qualified_low.csv")
        results2 = qualify(sample_leads_csv, output2, min_score=10)
        low_count = len(results2)

        assert low_count >= high_count

    def test_qualify_sorted_by_score_descending(self, sample_leads_csv, tmp_path):
        output = str(tmp_path / "qualified_sorted.csv")
        results = qualify(sample_leads_csv, output, min_score=0)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_qualify_saves_output(self, sample_leads_csv, tmp_path):
        output = str(tmp_path / "qualified_save.csv")
        qualify(sample_leads_csv, output, min_score=30)
        assert Path(output).exists()


class TestConstants:
    def test_major_cities_include_key_markets(self):
        assert "ho chi minh" in MAJOR_CITIES
        assert "ha noi" in MAJOR_CITIES or "hanoi" in MAJOR_CITIES
        assert "da nang" in MAJOR_CITIES or "danang" in MAJOR_CITIES

    def test_ecom_platforms_include_top_3(self):
        assert "shopee" in ECOM_PLATFORMS
        assert "lazada" in ECOM_PLATFORMS
        assert "tiktok_shop" in ECOM_PLATFORMS or "tiktok" in ECOM_PLATFORMS

    def test_default_min_score(self):
        assert DEFAULT_MIN_SCORE == 30
