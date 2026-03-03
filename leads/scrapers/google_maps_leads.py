"""
Google Maps Business Lead Scraper
==================================
Scrapes business listings from Google Maps for a given category and city.
Extracts: business name, address, phone, website, and platform indicators.

Usage:
    python google_maps_leads.py --category "shop thoi trang" --city "Ho Chi Minh" --count 20
    python google_maps_leads.py --category "shop my pham" --city "Ha Noi" --count 50

Requirements:
    pip install requests beautifulsoup4 lxml

Note:
    Google Maps does not have an official public scraping API. This script uses
    search result page parsing. For production use at scale, consider the
    Google Places API (paid) or a proxy rotation service. Rate limiting and
    User-Agent rotation are implemented to reduce blocking risk.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import List, Optional
from urllib.parse import quote_plus, urlencode

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]

ECOMMERCE_KEYWORDS = [
    "shop", "store", "cửa hàng", "thời trang", "mỹ phẩm", "quần áo",
    "giày dép", "túi xách", "điện tử", "điện thoại", "đồng hồ",
    "phụ kiện", "mẹ bé", "đồ chơi", "gia dụng", "nội thất",
    "shopee", "tiktok", "lazada", "sendo", "online", "order",
]

PLATFORM_PATTERNS = {
    "shopee": [r"shopee\.vn/", r"shopee", r"shop\.ee"],
    "tiktok_shop": [r"tiktok", r"tiktokshop", r"shop\.tiktok"],
    "lazada": [r"lazada\.vn/", r"lazada"],
}


@dataclass
class Lead:
    business_name: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    zalo: str = ""
    website: str = ""
    facebook: str = ""
    platform: str = ""
    city: str = ""
    address: str = ""
    category: str = ""
    source: str = "google_maps"
    score: int = 0
    status: str = "new"
    notes: str = ""
    scraped_date: str = field(default_factory=lambda: str(date.today()))


class LeadScraper:
    """Scrapes business leads from Google Maps search results."""

    BASE_URL = "https://www.google.com/maps/search/"
    SEARCH_URL = "https://www.google.com/search"

    def __init__(self, category: str, city: str, count: int = 20):
        self.category = category
        self.city = city
        self.count = count
        self.leads: List[Lead] = []
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
        })
        return session

    def _rotate_user_agent(self):
        """Rotate user agent to reduce detection risk."""
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)

    def _sleep_random(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """Sleep a random amount to mimic human browsing patterns."""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Sleeping {delay:.1f}s")
        time.sleep(delay)

    def _build_search_query(self, start: int = 0) -> str:
        """Build the Google search URL for local business results."""
        query = f"{self.category} {self.city} Vietnam"
        params = {
            "q": query,
            "tbm": "lcl",  # local search
            "start": start,
            "hl": "vi",
            "gl": "vn",
        }
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _extract_phone_numbers(self, text: str) -> List[str]:
        """Extract Vietnamese phone numbers from text."""
        patterns = [
            r"(?:0|\+84)\s*[3-9]\d{1}\s*\d{3}\s*\d{4}",
            r"(?:0|\+84)[3-9]\d{8}",
            r"0[1-9][0-9]{8}",
        ]
        phones = []
        for pattern in patterns:
            found = re.findall(pattern, text.replace(" ", ""))
            phones.extend(found)
        # Normalize: remove spaces, ensure starts with 0
        normalized = []
        for p in phones:
            p = re.sub(r"\s+", "", p)
            if p.startswith("+84"):
                p = "0" + p[3:]
            if p not in normalized:
                normalized.append(p)
        return normalized

    def _extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text."""
        pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        emails = re.findall(pattern, text)
        # Filter out common false positives
        excluded_domains = ["example.com", "test.com", "domain.com", "email.com"]
        return [e for e in emails if not any(d in e for d in excluded_domains)]

    def _detect_platform(self, text: str, website: str = "") -> str:
        """Detect which e-commerce platforms a business uses."""
        combined = (text + " " + website).lower()
        detected = []
        for platform, patterns in PLATFORM_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, combined, re.IGNORECASE):
                    detected.append(platform)
                    break
        return ", ".join(detected) if detected else ""

    def _extract_facebook_url(self, text: str) -> str:
        """Extract Facebook page URL from text."""
        pattern = r"https?://(?:www\.)?facebook\.com/[a-zA-Z0-9._\-/]+"
        match = re.search(pattern, text)
        return match.group(0) if match else ""

    def _parse_google_local_result(self, result_div) -> Optional[Lead]:
        """Parse a single Google local search result block."""
        try:
            lead = Lead(category=self.category, city=self.city)

            # Business name
            name_elem = result_div.find(class_=re.compile(r"OSrXXb|dbg0pd|LC20lb"))
            if not name_elem:
                name_elem = result_div.find("h3")
            if name_elem:
                lead.business_name = name_elem.get_text(strip=True)
            else:
                return None

            full_text = result_div.get_text(separator=" ")

            # Address
            address_elem = result_div.find(class_=re.compile(r"rllt__details|lqhpac"))
            if address_elem:
                spans = address_elem.find_all("span")
                if spans:
                    lead.address = spans[0].get_text(strip=True)

            # Phone
            phones = self._extract_phone_numbers(full_text)
            if phones:
                lead.phone = phones[0]
                lead.zalo = phones[0]  # Zalo usually same as phone in Vietnam

            # Email
            emails = self._extract_emails(full_text)
            if emails:
                lead.email = emails[0]

            # Website link
            link_elem = result_div.find("a", href=re.compile(r"^https?://"))
            if link_elem:
                href = link_elem.get("href", "")
                # Skip Google-internal links
                if "google.com" not in href and "maps.google" not in href:
                    lead.website = href

            # Platform detection
            lead.platform = self._detect_platform(full_text, lead.website)

            # Facebook
            lead.facebook = self._extract_facebook_url(full_text)

            return lead

        except Exception as e:
            logger.warning(f"Error parsing result: {e}")
            return None

    def _fetch_business_detail_page(self, url: str) -> Optional[str]:
        """Fetch a business's own website for additional contact info."""
        if not url or "google.com" in url:
            return None
        try:
            self._rotate_user_agent()
            resp = self.session.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            logger.debug(f"Could not fetch {url}: {e}")
        return None

    def _enrich_from_website(self, lead: Lead) -> Lead:
        """Try to get more contact info from the business's own website."""
        if not lead.website:
            return lead
        html = self._fetch_business_detail_page(lead.website)
        if not html:
            return lead
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ")

        if not lead.email:
            emails = self._extract_emails(text)
            if emails:
                lead.email = emails[0]

        if not lead.phone:
            phones = self._extract_phone_numbers(text)
            if phones:
                lead.phone = phones[0]
                lead.zalo = phones[0]

        if not lead.platform:
            lead.platform = self._detect_platform(text, lead.website)

        if not lead.facebook:
            lead.facebook = self._extract_facebook_url(text)

        return lead

    def search(self) -> List[Lead]:
        """
        Execute the search and collect leads up to self.count.
        Paginates through results pages as needed.
        """
        collected = 0
        start = 0
        page_size = 10

        logger.info(f"Searching for '{self.category}' in '{self.city}' (target: {self.count} leads)")

        while collected < self.count:
            url = self._build_search_query(start=start)
            logger.info(f"Fetching page (start={start}): {url}")

            try:
                self._rotate_user_agent()
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                break

            soup = BeautifulSoup(response.text, "lxml")

            # Try multiple selectors for different Google result formats
            result_blocks = (
                soup.find_all("div", class_=re.compile(r"VkpGBb|uMdZh|tF2Cxc")) or
                soup.find_all("div", attrs={"data-rc-exp": True}) or
                soup.find_all(class_=re.compile(r"rllt__details|rhvv2a"))
            )

            if not result_blocks:
                # Fall back to broader search: look for any business card structure
                result_blocks = soup.find_all("div", recursive=True)
                result_blocks = [
                    b for b in result_blocks
                    if b.find("h3") and len(b.get_text()) > 50
                ][:page_size]

            if not result_blocks:
                logger.warning("No result blocks found on this page. Google may have changed their layout.")
                break

            page_leads = []
            for block in result_blocks:
                if collected + len(page_leads) >= self.count:
                    break
                lead = self._parse_google_local_result(block)
                if lead and lead.business_name:
                    page_leads.append(lead)

            if not page_leads:
                logger.info("No new leads on this page — stopping pagination.")
                break

            # Enrich each lead with website data (with rate limiting)
            for lead in page_leads:
                if lead.website:
                    logger.debug(f"Enriching lead: {lead.business_name}")
                    lead = self._enrich_from_website(lead)
                    self._sleep_random(1.0, 3.0)

            self.leads.extend(page_leads)
            collected += len(page_leads)
            logger.info(f"Collected {collected}/{self.count} leads so far")

            start += page_size
            self._sleep_random(3.0, 7.0)

        logger.info(f"Search complete. Total leads found: {len(self.leads)}")
        return self.leads

    def extract_contacts(self) -> List[Lead]:
        """
        Post-process leads to normalize and enrich contact info.
        This is called after search() to clean up the data.
        """
        cleaned = []
        seen_names = set()

        for lead in self.leads:
            # Deduplicate by business name
            name_key = re.sub(r"\s+", " ", lead.business_name.lower().strip())
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            # Normalize phone: remove spaces and dashes
            if lead.phone:
                lead.phone = re.sub(r"[\s\-\.]", "", lead.phone)
            if lead.zalo:
                lead.zalo = re.sub(r"[\s\-\.]", "", lead.zalo)

            # Clean website URL
            if lead.website and not lead.website.startswith("http"):
                lead.website = "https://" + lead.website

            cleaned.append(lead)

        self.leads = cleaned
        return cleaned

    def save_csv(self, output_dir: str = "leads/data") -> str:
        """
        Save leads to a CSV file.

        Returns the path to the saved file.
        """
        os.makedirs(output_dir, exist_ok=True)

        city_slug = self.city.lower().replace(" ", "_")
        category_slug = self.category.lower().replace(" ", "_")
        today = date.today().isoformat()
        filename = f"{city_slug}_{category_slug}_{today}.csv"
        filepath = os.path.join(output_dir, filename)

        if not self.leads:
            logger.warning("No leads to save.")
            return filepath

        fieldnames = [
            "business_name", "contact_name", "email", "phone", "zalo",
            "website", "facebook", "platform", "city", "address",
            "category", "source", "score", "status", "notes", "scraped_date",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for lead in self.leads:
                writer.writerow(asdict(lead))

        logger.info(f"Saved {len(self.leads)} leads to {filepath}")
        return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps for e-commerce business leads in Vietnam"
    )
    parser.add_argument(
        "--category",
        required=True,
        help='Business category to search for (e.g. "shop thoi trang", "shop my pham")',
    )
    parser.add_argument(
        "--city",
        required=True,
        help='City to search in (e.g. "Ho Chi Minh", "Ha Noi", "Da Nang")',
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of leads to collect (default: 20)",
    )
    parser.add_argument(
        "--output-dir",
        default="leads/data",
        help="Directory to save the output CSV (default: leads/data)",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Visit each business website to enrich contact info (slower)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    scraper = LeadScraper(
        category=args.category,
        city=args.city,
        count=args.count,
    )

    leads = scraper.search()

    if leads:
        scraper.extract_contacts()
        output_path = scraper.save_csv(output_dir=args.output_dir)
        print(f"\nDone! {len(scraper.leads)} leads saved to: {output_path}")
        print("\nSample leads:")
        for lead in scraper.leads[:3]:
            print(f"  - {lead.business_name} | {lead.phone} | {lead.email} | {lead.website}")
    else:
        print("No leads found. Try different category/city terms.")
        sys.exit(1)


if __name__ == "__main__":
    main()
