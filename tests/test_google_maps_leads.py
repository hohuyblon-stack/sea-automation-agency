"""
Tests for leads/scrapers/google_maps_leads.py — Google Maps lead scraper.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from leads.scrapers.google_maps_leads import (
    ECOMMERCE_KEYWORDS,
    PLATFORM_PATTERNS,
    USER_AGENTS,
    Lead,
    LeadScraper,
)


class TestLead:
    def test_default_values(self):
        lead = Lead()
        assert lead.business_name == ""
        assert lead.source == "google_maps"
        assert lead.status == "new"
        assert lead.score == 0

    def test_custom_values(self):
        lead = Lead(business_name="Test Shop", city="HCM", platform="shopee")
        assert lead.business_name == "Test Shop"
        assert lead.city == "HCM"
        assert lead.platform == "shopee"


class TestLeadScraper:
    def setup_method(self):
        self.scraper = LeadScraper(category="shop thoi trang", city="Ho Chi Minh", count=5)

    def test_init(self):
        assert self.scraper.category == "shop thoi trang"
        assert self.scraper.city == "Ho Chi Minh"
        assert self.scraper.count == 5
        assert self.scraper.leads == []

    def test_create_session_sets_headers(self):
        session = self.scraper._create_session()
        assert "User-Agent" in session.headers
        assert "Accept-Language" in session.headers
        assert "vi-VN" in session.headers["Accept-Language"]

    def test_rotate_user_agent(self):
        original_ua = self.scraper.session.headers["User-Agent"]
        # Rotate many times to ensure it changes at least once
        changed = False
        for _ in range(20):
            self.scraper._rotate_user_agent()
            if self.scraper.session.headers["User-Agent"] != original_ua:
                changed = True
                break
        # With 6 user agents, the probability of not changing in 20 tries is negligible
        assert changed or len(USER_AGENTS) == 1

    def test_build_search_query(self):
        url = self.scraper._build_search_query(start=0)
        assert "google.com/search" in url
        assert "tbm=lcl" in url
        assert "hl=vi" in url
        assert "gl=vn" in url
        assert "shop+thoi+trang" in url or "shop%20thoi%20trang" in url

    def test_build_search_query_pagination(self):
        url = self.scraper._build_search_query(start=10)
        assert "start=10" in url

    def test_extract_phone_numbers_standard(self):
        phones = self.scraper._extract_phone_numbers("Call 0901234567 for info")
        assert "0901234567" in phones

    def test_extract_phone_numbers_with_country_code(self):
        phones = self.scraper._extract_phone_numbers("Phone: +84901234567")
        assert "0901234567" in phones

    def test_extract_phone_numbers_with_spaces(self):
        phones = self.scraper._extract_phone_numbers("0901 234 567")
        assert len(phones) >= 1

    def test_extract_phone_numbers_no_phone(self):
        phones = self.scraper._extract_phone_numbers("No phone number here")
        assert phones == []

    def test_extract_phone_numbers_deduplicates(self):
        phones = self.scraper._extract_phone_numbers("0901234567 0901234567")
        assert len(phones) == 1

    def test_extract_emails(self):
        emails = self.scraper._extract_emails("Contact us at shop@store.vn or info@gmail.com")
        assert "shop@store.vn" in emails
        assert "info@gmail.com" in emails

    def test_extract_emails_filters_false_positives(self):
        emails = self.scraper._extract_emails("test@example.com user@test.com")
        assert "test@example.com" not in emails
        assert "user@test.com" not in emails

    def test_extract_emails_no_emails(self):
        emails = self.scraper._extract_emails("No email here, just text")
        assert emails == []

    def test_detect_platform_shopee(self):
        platform = self.scraper._detect_platform("Visit our shopee.vn/shop123")
        assert "shopee" in platform

    def test_detect_platform_tiktok(self):
        platform = self.scraper._detect_platform("Follow us on tiktokshop")
        assert "tiktok" in platform

    def test_detect_platform_lazada(self):
        platform = self.scraper._detect_platform("Buy on lazada.vn/store")
        assert "lazada" in platform

    def test_detect_platform_multiple(self):
        platform = self.scraper._detect_platform("shopee.vn lazada.vn")
        assert "shopee" in platform
        assert "lazada" in platform

    def test_detect_platform_from_website(self):
        platform = self.scraper._detect_platform("", website="https://shopee.vn/myshop")
        assert "shopee" in platform

    def test_detect_platform_none(self):
        platform = self.scraper._detect_platform("Just a regular text")
        assert platform == ""

    def test_extract_facebook_url(self):
        url = self.scraper._extract_facebook_url("Follow us at https://www.facebook.com/myshop")
        assert url == "https://www.facebook.com/myshop"

    def test_extract_facebook_url_no_match(self):
        url = self.scraper._extract_facebook_url("No social media links here")
        assert url == ""

    def test_extract_contacts_deduplicates(self):
        self.scraper.leads = [
            Lead(business_name="Shop A", phone="0901234567"),
            Lead(business_name="Shop A", phone="0901234567"),  # duplicate
            Lead(business_name="Shop B", phone="0912345678"),
        ]
        cleaned = self.scraper.extract_contacts()
        assert len(cleaned) == 2

    def test_extract_contacts_normalizes_phone(self):
        self.scraper.leads = [
            Lead(business_name="Shop A", phone="090-123-4567"),
        ]
        cleaned = self.scraper.extract_contacts()
        assert cleaned[0].phone == "0901234567"

    def test_extract_contacts_normalizes_website(self):
        self.scraper.leads = [
            Lead(business_name="Shop A", website="shop.vn"),
        ]
        cleaned = self.scraper.extract_contacts()
        assert cleaned[0].website == "https://shop.vn"

    def test_save_csv(self, tmp_path):
        self.scraper.leads = [
            Lead(business_name="Test Shop", phone="0901234567", city="HCM"),
        ]
        filepath = self.scraper.save_csv(output_dir=str(tmp_path))
        assert Path(filepath).exists()

    def test_save_csv_empty(self, tmp_path):
        filepath = self.scraper.save_csv(output_dir=str(tmp_path))
        assert not Path(filepath).exists() or Path(filepath).stat().st_size == 0

    def test_save_csv_filename_format(self, tmp_path):
        self.scraper.leads = [Lead(business_name="Test")]
        filepath = self.scraper.save_csv(output_dir=str(tmp_path))
        name = Path(filepath).name
        assert "ho_chi_minh" in name
        assert "shop_thoi_trang" in name


class TestConstants:
    def test_user_agents_not_empty(self):
        assert len(USER_AGENTS) > 0

    def test_ecommerce_keywords_include_vietnamese(self):
        assert "cửa hàng" in ECOMMERCE_KEYWORDS
        assert "thời trang" in ECOMMERCE_KEYWORDS

    def test_platform_patterns_include_top_3(self):
        assert "shopee" in PLATFORM_PATTERNS
        assert "tiktok_shop" in PLATFORM_PATTERNS
        assert "lazada" in PLATFORM_PATTERNS
