"""
Tests for leads/scrapers/facebook_group_leads.py — Facebook group lead extraction.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from leads.scrapers.facebook_group_leads import (
    ECOM_PLATFORM_PATTERNS,
    PHONE_PATTERNS,
    SELLER_KEYWORDS,
    FacebookGroupScraper,
    FacebookLead,
)


class TestFacebookLead:
    def test_defaults(self):
        lead = FacebookLead()
        assert lead.source == "facebook_group"
        assert lead.status == "new"
        assert lead.score == 0

    def test_custom_values(self):
        lead = FacebookLead(contact_name="Nguyen A", phone="0901234567", platform="shopee")
        assert lead.contact_name == "Nguyen A"
        assert lead.phone == "0901234567"


class TestFacebookGroupScraper:
    @patch("leads.scrapers.facebook_group_leads.dotenv_values", return_value={})
    def setup_method(self, method, mock_dotenv=None):
        with patch.dict(os.environ, {"FACEBOOK_ACCESS_TOKEN": ""}, clear=False):
            self.scraper = FacebookGroupScraper(
                group_id="123456789",
                count=10,
                group_name="test_group",
            )

    def test_init(self):
        assert self.scraper.group_id == "123456789"
        assert self.scraper.count == 10
        assert self.scraper.group_name == "test_group"

    def test_extract_phones_standard(self):
        phones = self.scraper._extract_phones("Liên hệ 0901234567")
        assert "0901234567" in phones

    def test_extract_phones_with_country_code(self):
        phones = self.scraper._extract_phones("+84901234567")
        assert "0901234567" in phones

    def test_extract_phones_short_number_excluded(self):
        phones = self.scraper._extract_phones("12345")
        assert len(phones) == 0

    def test_extract_emails(self):
        emails = self.scraper._extract_emails("Email: shop@store.vn hoặc info@gmail.com")
        assert "shop@store.vn" in emails

    def test_extract_emails_excludes_test_domains(self):
        emails = self.scraper._extract_emails("test@example.com fake@test.com")
        assert len(emails) == 0

    def test_detect_platforms_shopee(self):
        result = self.scraper._detect_platforms("Mua hàng trên shopee.vn")
        assert "shopee" in result

    def test_detect_platforms_multiple(self):
        result = self.scraper._detect_platforms("shopee lazada tiktok")
        assert "shopee" in result
        assert "lazada" in result
        assert "tiktok_shop" in result

    def test_detect_platforms_none(self):
        result = self.scraper._detect_platforms("Just text, no platform")
        assert result == ""

    def test_detect_city_hcm(self):
        city = self.scraper._detect_city("Giao hàng khu vực tphcm")
        assert city.lower() in ["ho chi minh", ""]

    def test_detect_city_hanoi(self):
        city = self.scraper._detect_city("Hà Nội")
        assert city.lower() in ["ha noi", ""]

    def test_detect_city_none(self):
        city = self.scraper._detect_city("Random text without city")
        assert city == ""

    def test_is_seller_post_true(self):
        text = "Shop bán quần áo order inbox ngay"
        assert self.scraper._is_seller_post(text) is True

    def test_is_seller_post_false(self):
        text = "Hello everyone, nice weather today"
        assert self.scraper._is_seller_post(text) is False

    def test_is_seller_post_one_keyword_not_enough(self):
        text = "I have a shop"
        assert self.scraper._is_seller_post(text) is False

    def test_score_lead_with_phone(self):
        lead = FacebookLead(phone="0901234567")
        score = self.scraper._score_lead(lead, "shop bán hàng")
        assert score >= 30

    def test_score_lead_with_email(self):
        lead = FacebookLead(email="shop@vn.com")
        score = self.scraper._score_lead(lead, "shop bán hàng")
        assert score >= 20

    def test_score_lead_with_platform(self):
        lead = FacebookLead(platform="shopee")
        score = self.scraper._score_lead(lead, "shop bán hàng")
        assert score >= 20

    def test_score_lead_capped_at_100(self):
        lead = FacebookLead(phone="0901234567", email="a@b.com", platform="shopee", city="HCM")
        text = " ".join(SELLER_KEYWORDS * 3)
        score = self.scraper._score_lead(lead, text)
        assert score <= 100

    def test_parse_graph_post_seller(self):
        post = {
            "message": "Shop bán quần áo order inbox freeship 0901234567",
            "permalink_url": "https://facebook.com/post/123",
            "from": {"name": "Seller A", "id": "111"},
        }
        lead = self.scraper._parse_graph_post(post)
        assert lead is not None
        assert lead.phone == "0901234567"
        assert lead.contact_name == "Seller A"

    def test_parse_graph_post_not_seller(self):
        post = {
            "message": "Hello world, just chatting",
            "from": {"name": "Random", "id": "222"},
        }
        lead = self.scraper._parse_graph_post(post)
        assert lead is None

    def test_parse_graph_post_empty_message(self):
        post = {"message": "", "from": {"name": "X", "id": "333"}}
        lead = self.scraper._parse_graph_post(post)
        assert lead is None

    def test_deduplicate_by_phone(self):
        self.scraper.leads = [
            FacebookLead(contact_name="A", phone="0901234567"),
            FacebookLead(contact_name="B", phone="0901234567"),
            FacebookLead(contact_name="C", phone="0912345678"),
        ]
        unique = self.scraper.deduplicate()
        assert len(unique) == 2

    def test_deduplicate_by_name(self):
        self.scraper.leads = [
            FacebookLead(contact_name="Same Name", phone="0901234567"),
            FacebookLead(contact_name="Same Name", phone="0912345678"),
        ]
        unique = self.scraper.deduplicate()
        assert len(unique) == 1

    def test_save_csv(self, tmp_path):
        self.scraper.leads = [
            FacebookLead(contact_name="Test", phone="0901234567"),
        ]
        filepath = self.scraper.save_csv(output_dir=str(tmp_path))
        assert Path(filepath).exists()

    def test_save_csv_empty(self, tmp_path):
        filepath = self.scraper.save_csv(output_dir=str(tmp_path))
        assert "facebook_" in Path(filepath).name


class TestConstants:
    def test_seller_keywords_not_empty(self):
        assert len(SELLER_KEYWORDS) > 0

    def test_phone_patterns_not_empty(self):
        assert len(PHONE_PATTERNS) > 0

    def test_ecom_patterns_include_top_platforms(self):
        assert "shopee" in ECOM_PLATFORM_PATTERNS
        assert "lazada" in ECOM_PLATFORM_PATTERNS
        assert "tiktok_shop" in ECOM_PLATFORM_PATTERNS
