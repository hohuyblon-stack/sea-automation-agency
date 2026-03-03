"""
Facebook Group Lead Extractor
==============================
Extracts e-commerce seller leads from Vietnamese Facebook group posts.
Targets groups where sellers advertise products or ask for suppliers.

Usage:
    python facebook_group_leads.py --group-id 123456789 --count 50
    python facebook_group_leads.py --group-url "https://www.facebook.com/groups/shopee.sellers.vn" --count 30

Requirements:
    pip install requests beautifulsoup4 lxml python-dotenv

Note:
    This script uses the Facebook Graph API (Page/Group Feed endpoint).
    You need a Facebook Developer App with user access token.
    Set FACEBOOK_ACCESS_TOKEN in your .env file.

    Alternatively, set SCRAPE_MODE=manual in .env to parse exported HTML
    from a group page (download the page manually, pass with --html-file).
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
import random
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

import requests
from dotenv import dotenv_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path.home() / "sea-automation-agency"
ENV_PATH = BASE_DIR / ".env"

# Vietnamese seller keywords that indicate an active e-commerce seller
SELLER_KEYWORDS = [
    "shop", "cửa hàng", "bán", "order", "inbox", "đặt hàng",
    "shopee", "tiktok", "lazada", "sendo", "tiki",
    "ship", "cod", "freeship", "đơn hàng", "kho",
    "sỉ", "lẻ", "giá sỉ", "buôn", "nhập hàng",
    "tồn kho", "hàng về", "hàng mới",
]

PHONE_PATTERNS = [
    r"(?:0|\+84)\s*[3-9]\d{1}\s*\d{3}\s*\d{4}",
    r"(?:0|\+84)[3-9]\d{8}",
    r"0[1-9][0-9]{8}",
]

ECOM_PLATFORM_PATTERNS = {
    "shopee": [r"shopee\.vn", r"shopee\.com", r"\bshopee\b"],
    "tiktok_shop": [r"tiktok\.com", r"tiktokshop", r"shop\.tiktok", r"\btiktok\b"],
    "lazada": [r"lazada\.vn", r"lazada\.com", r"\blazada\b"],
    "sendo": [r"sendo\.vn", r"\bsendo\b"],
    "tiki": [r"tiki\.vn", r"\btiki\b"],
}


@dataclass
class FacebookLead:
    business_name: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    zalo: str = ""
    facebook_profile: str = ""
    platform: str = ""
    city: str = ""
    post_text: str = ""
    post_url: str = ""
    source: str = "facebook_group"
    group_name: str = ""
    score: int = 0
    status: str = "new"
    notes: str = ""
    scraped_date: str = field(default_factory=lambda: str(date.today()))


class FacebookGroupScraper:
    """
    Extract leads from Facebook Groups using the Graph API.
    Falls back to manual HTML parsing if API is unavailable.
    """

    GRAPH_API_BASE = "https://graph.facebook.com/v18.0"

    def __init__(self, group_id: str, count: int = 50, group_name: str = ""):
        self.group_id = group_id
        self.count = count
        self.group_name = group_name
        self.leads: List[FacebookLead] = []
        self.env = dotenv_values(str(ENV_PATH))
        self.access_token = self.env.get("FACEBOOK_ACCESS_TOKEN", "") or os.environ.get("FACEBOOK_ACCESS_TOKEN", "")
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        return session

    def _sleep(self, min_sec: float = 1.0, max_sec: float = 3.0):
        time.sleep(random.uniform(min_sec, max_sec))

    # ------------------------------------------------------------------
    # Phone / email / platform extraction helpers
    # ------------------------------------------------------------------

    def _extract_phones(self, text: str) -> List[str]:
        phones = []
        for pattern in PHONE_PATTERNS:
            found = re.findall(pattern, text.replace(" ", ""))
            phones.extend(found)
        normalized = []
        for p in phones:
            p = re.sub(r"\s+", "", p)
            if p.startswith("+84"):
                p = "0" + p[3:]
            if p not in normalized and len(p) >= 10:
                normalized.append(p)
        return normalized

    def _extract_emails(self, text: str) -> List[str]:
        pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        emails = re.findall(pattern, text)
        excluded = ["example.com", "test.com", "domain.com"]
        return [e for e in emails if not any(d in e for d in excluded)]

    def _detect_platforms(self, text: str) -> str:
        detected = []
        text_lower = text.lower()
        for platform, patterns in ECOM_PLATFORM_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text_lower):
                    detected.append(platform)
                    break
        return ", ".join(detected)

    def _detect_city(self, text: str) -> str:
        cities = {
            "ho chi minh": ["hcm", "hồ chí minh", "saigon", "sài gòn", "tphcm", "tp.hcm"],
            "ha noi": ["hà nội", "hanoi", "hn"],
            "da nang": ["đà nẵng", "danang", "dn"],
            "can tho": ["cần thơ", "canto"],
            "hai phong": ["hải phòng", "haiphong"],
            "bien hoa": ["biên hòa"],
            "vung tau": ["vũng tàu"],
            "nha trang": ["nha trang"],
            "hue": ["huế", "hue"],
        }
        text_lower = text.lower()
        for city_name, variants in cities.items():
            if any(v in text_lower for v in variants):
                return city_name.title()
        return ""

    def _score_lead(self, lead: FacebookLead, post_text: str) -> int:
        """Score the lead quality based on available data."""
        score = 0
        if lead.phone:
            score += 30
        if lead.email:
            score += 20
        if lead.platform:
            score += 20
        if lead.city:
            score += 10
        text_lower = post_text.lower()
        keyword_hits = sum(1 for kw in SELLER_KEYWORDS if kw in text_lower)
        score += min(keyword_hits * 3, 20)
        return min(score, 100)

    def _is_seller_post(self, text: str) -> bool:
        """Check if the post looks like it's from an active seller."""
        text_lower = text.lower()
        keyword_hits = sum(1 for kw in SELLER_KEYWORDS if kw in text_lower)
        return keyword_hits >= 2

    # ------------------------------------------------------------------
    # Graph API method
    # ------------------------------------------------------------------

    def _fetch_via_graph_api(self) -> List[dict]:
        """Fetch group posts via Facebook Graph API."""
        if not self.access_token:
            logger.warning("No FACEBOOK_ACCESS_TOKEN found. Cannot use Graph API.")
            return []

        posts = []
        url = f"{self.GRAPH_API_BASE}/{self.group_id}/feed"
        params = {
            "access_token": self.access_token,
            "fields": "message,from,created_time,permalink_url",
            "limit": min(self.count * 2, 100),  # fetch extra to account for non-seller posts
        }

        while len(posts) < self.count * 2:
            try:
                resp = self.session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.error(f"Graph API request failed: {e}")
                break
            except json.JSONDecodeError:
                logger.error("Graph API returned non-JSON response")
                break

            batch = data.get("data", [])
            if not batch:
                break

            posts.extend(batch)
            logger.info(f"Fetched {len(posts)} posts so far...")

            # Pagination
            next_page = data.get("paging", {}).get("next")
            if not next_page or len(posts) >= self.count * 2:
                break

            url = next_page
            params = {}  # next_page URL already has params
            self._sleep(1.0, 2.0)

        return posts

    def _parse_graph_post(self, post: dict) -> Optional[FacebookLead]:
        """Convert a Graph API post dict into a FacebookLead."""
        message = post.get("message", "")
        if not message or not self._is_seller_post(message):
            return None

        lead = FacebookLead(
            post_text=message[:500],  # Truncate for storage
            post_url=post.get("permalink_url", ""),
            group_name=self.group_name,
        )

        # Contact name from the "from" field
        from_info = post.get("from", {})
        lead.contact_name = from_info.get("name", "")
        lead.facebook_profile = f"https://www.facebook.com/{from_info.get('id', '')}"

        # Extract contact details
        phones = self._extract_phones(message)
        if phones:
            lead.phone = phones[0]
            lead.zalo = phones[0]

        emails = self._extract_emails(message)
        if emails:
            lead.email = emails[0]

        lead.platform = self._detect_platforms(message)
        lead.city = self._detect_city(message)

        # Use contact name as business name if no better info
        lead.business_name = lead.contact_name or "Unknown"

        lead.score = self._score_lead(lead, message)
        return lead

    # ------------------------------------------------------------------
    # Manual HTML parsing fallback
    # ------------------------------------------------------------------

    def parse_html_file(self, html_file: str) -> List[FacebookLead]:
        """
        Parse a manually saved Facebook group HTML page.
        Use this when Graph API is unavailable.

        To get the HTML:
        1. Open the Facebook group in browser
        2. Scroll down to load more posts
        3. Save the page as HTML (File > Save Page As)
        4. Pass the saved file with --html-file
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("Install beautifulsoup4: pip install beautifulsoup4 lxml")
            return []

        path = Path(html_file)
        if not path.exists():
            logger.error(f"HTML file not found: {html_file}")
            return []

        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")

        leads = []
        # Look for post text blocks (div with long text content)
        post_divs = soup.find_all("div", attrs={"data-ad-preview": "message"})
        if not post_divs:
            # Fallback: find any div with substantial Vietnamese text
            all_divs = soup.find_all("div")
            post_divs = [
                d for d in all_divs
                if d.get_text() and len(d.get_text()) > 100
                and any(kw in d.get_text().lower() for kw in SELLER_KEYWORDS)
            ][:self.count * 3]

        logger.info(f"Found {len(post_divs)} potential post blocks in HTML")

        for div in post_divs:
            text = div.get_text(separator=" ")
            if not self._is_seller_post(text):
                continue

            lead = FacebookLead(
                post_text=text[:500],
                group_name=self.group_name,
                source="facebook_group_html",
            )

            phones = self._extract_phones(text)
            if phones:
                lead.phone = phones[0]
                lead.zalo = phones[0]

            emails = self._extract_emails(text)
            if emails:
                lead.email = emails[0]

            lead.platform = self._detect_platforms(text)
            lead.city = self._detect_city(text)
            lead.score = self._score_lead(lead, text)

            if lead.phone or lead.email:
                leads.append(lead)

            if len(leads) >= self.count:
                break

        logger.info(f"Extracted {len(leads)} leads from HTML file")
        return leads

    # ------------------------------------------------------------------
    # Main scrape method
    # ------------------------------------------------------------------

    def scrape(self) -> List[FacebookLead]:
        """Run the scraper and return leads."""
        logger.info(f"Scraping Facebook group {self.group_id} (target: {self.count} leads)")

        if self.access_token:
            raw_posts = self._fetch_via_graph_api()
            for post in raw_posts:
                if len(self.leads) >= self.count:
                    break
                lead = self._parse_graph_post(post)
                if lead and (lead.phone or lead.email):
                    self.leads.append(lead)
            logger.info(f"Extracted {len(self.leads)} leads from Graph API")
        else:
            logger.warning(
                "No Facebook access token. Falling back to manual HTML mode.\n"
                "Set FACEBOOK_ACCESS_TOKEN in .env, or use --html-file to parse a saved page."
            )

        return self.leads

    def deduplicate(self) -> List[FacebookLead]:
        """Remove duplicate leads by phone number."""
        seen_phones = set()
        seen_names = set()
        unique = []
        for lead in self.leads:
            key_phone = re.sub(r"\s", "", lead.phone) if lead.phone else None
            key_name = lead.contact_name.lower().strip() if lead.contact_name else None

            if key_phone and key_phone in seen_phones:
                continue
            if key_name and key_name in seen_names:
                continue

            if key_phone:
                seen_phones.add(key_phone)
            if key_name:
                seen_names.add(key_name)
            unique.append(lead)

        self.leads = unique
        return unique

    def save_csv(self, output_dir: str = "leads/data") -> str:
        """Save leads to CSV file."""
        os.makedirs(output_dir, exist_ok=True)
        group_slug = re.sub(r"\W+", "_", self.group_id)[:30]
        today = date.today().isoformat()
        filename = f"facebook_{group_slug}_{today}.csv"
        filepath = os.path.join(output_dir, filename)

        if not self.leads:
            logger.warning("No leads to save.")
            return filepath

        fieldnames = [
            "business_name", "contact_name", "email", "phone", "zalo",
            "facebook_profile", "platform", "city", "post_text", "post_url",
            "source", "group_name", "score", "status", "notes", "scraped_date",
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
        description="Extract leads from Facebook groups for Vietnamese e-commerce sellers"
    )
    parser.add_argument("--group-id", default="", help="Facebook Group ID (numeric)")
    parser.add_argument("--group-url", default="", help="Facebook Group URL (to extract ID)")
    parser.add_argument("--group-name", default="", help="Human-readable group name for notes")
    parser.add_argument("--count", type=int, default=30, help="Number of leads to collect")
    parser.add_argument("--html-file", default="", help="Path to manually saved group HTML file")
    parser.add_argument("--output-dir", default="leads/data", help="Output directory for CSV")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Extract group ID from URL if provided
    group_id = args.group_id
    if not group_id and args.group_url:
        match = re.search(r"groups/([^/?]+)", args.group_url)
        if match:
            group_id = match.group(1)
        else:
            logger.error("Could not extract group ID from URL")
            sys.exit(1)

    if not group_id and not args.html_file:
        parser.error("Provide --group-id, --group-url, or --html-file")

    group_id = group_id or "manual"
    scraper = FacebookGroupScraper(
        group_id=group_id,
        count=args.count,
        group_name=args.group_name or group_id,
    )

    if args.html_file:
        scraper.leads = scraper.parse_html_file(args.html_file)
    else:
        scraper.scrape()

    scraper.deduplicate()
    output_path = scraper.save_csv(output_dir=args.output_dir)

    print(f"\nDone! {len(scraper.leads)} leads saved to: {output_path}")
    if scraper.leads:
        print("\nTop leads:")
        for lead in sorted(scraper.leads, key=lambda l: l.score, reverse=True)[:5]:
            print(f"  - {lead.contact_name} | {lead.phone} | {lead.platform} | score={lead.score}")


if __name__ == "__main__":
    main()
