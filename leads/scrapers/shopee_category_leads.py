#!/usr/bin/env python3
"""
Shopee Category Lead Scraper (via Apify)
=========================================
Uses the Apify Shopee Scraper to pull top sellers from a given category
on Shopee Vietnam, then outputs leads in the standard CSV format used by
the rest of the SEA Agency pipeline.

Requirements:
    pip install requests python-dotenv

Environment:
    APIFY_API_TOKEN  — your Apify API token (set in .env)

Usage:
    python leads/scrapers/shopee_category_leads.py \
        --category "thoi trang nu" \
        --count 30 \
        --output-dir leads/data

    python leads/scrapers/shopee_category_leads.py \
        --category "my pham" \
        --city "Ho Chi Minh" \
        --count 50

The script calls the Apify Shopee Scraper actor, waits for the run to
finish, downloads the results, and maps them to the standard Lead CSV.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date

import requests
from dotenv import dotenv_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Apify configuration
# ---------------------------------------------------------------------------

# The default Apify actor for Shopee scraping.
# You can swap this for any Shopee scraper actor on the Apify marketplace.
DEFAULT_ACTOR_ID = "jupri/shopee-scraper"

APIFY_BASE_URL = "https://api.apify.com/v2"

# Mapping of Vietnamese category keywords to Shopee search terms / category URLs
CATEGORY_KEYWORDS = {
    "thoi trang": "thời trang",
    "thoi trang nu": "thời trang nữ",
    "thoi trang nam": "thời trang nam",
    "my pham": "mỹ phẩm",
    "dien tu": "điện tử",
    "do gia dung": "đồ gia dụng",
    "the thao": "thể thao",
    "suc khoe": "sức khỏe",
    "me va be": "mẹ và bé",
}

# Vietnamese city → Shopee location filter
CITY_TO_LOCATION = {
    "Ho Chi Minh": "Hồ Chí Minh",
    "Ha Noi": "Hà Nội",
    "Da Nang": "Đà Nẵng",
    "Hai Phong": "Hải Phòng",
    "Can Tho": "Cần Thơ",
    "Binh Duong": "Bình Dương",
    "Dong Nai": "Đồng Nai",
}


# ---------------------------------------------------------------------------
# Lead dataclass (matches all other scrapers)
# ---------------------------------------------------------------------------

@dataclass
class Lead:
    business_name: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    zalo: str = ""
    website: str = ""
    facebook: str = ""
    platform: str = "shopee"
    city: str = ""
    address: str = ""
    category: str = ""
    source: str = "shopee_category"
    score: int = 0
    status: str = "new"
    notes: str = ""
    scraped_date: str = field(default_factory=lambda: str(date.today()))


# ---------------------------------------------------------------------------
# Apify API helpers
# ---------------------------------------------------------------------------

def get_apify_token() -> str:
    """Load Apify API token from .env or environment."""
    env = dotenv_values()
    token = env.get("APIFY_API_TOKEN") or os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        logger.error(
            "APIFY_API_TOKEN not found.  Set it in .env or as an environment variable."
        )
        sys.exit(1)
    return token


def start_actor_run(actor_id: str, token: str, run_input: dict) -> str:
    """
    Start an Apify actor run and return the run ID.
    """
    url = f"{APIFY_BASE_URL}/acts/{actor_id}/runs"
    headers = {"Content-Type": "application/json"}
    params = {"token": token}

    logger.info(f"Starting Apify actor {actor_id} ...")
    resp = requests.post(url, headers=headers, params=params, json=run_input, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]
    run_id = data["id"]
    logger.info(f"Actor run started: {run_id} (status: {data['status']})")
    return run_id


def wait_for_run(run_id: str, token: str, poll_interval: int = 10, timeout: int = 300) -> dict:
    """
    Poll until the actor run finishes. Returns the run metadata dict.
    """
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
    params = {"token": token}
    elapsed = 0

    while elapsed < timeout:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data["status"]

        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            logger.info(f"Actor run {run_id} finished with status: {status}")
            if status != "SUCCEEDED":
                logger.error(f"Run did not succeed. Status: {status}")
                sys.exit(1)
            return data

        logger.info(f"  ... run {run_id} status: {status} (waited {elapsed}s)")
        time.sleep(poll_interval)
        elapsed += poll_interval

    logger.error(f"Timeout waiting for run {run_id} after {timeout}s")
    sys.exit(1)


def fetch_dataset_items(dataset_id: str, token: str) -> list[dict]:
    """
    Download all items from an Apify dataset.
    """
    url = f"{APIFY_BASE_URL}/datasets/{dataset_id}/items"
    params = {"token": token, "format": "json", "clean": "true"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json()
    logger.info(f"Fetched {len(items)} items from dataset {dataset_id}")
    return items


# ---------------------------------------------------------------------------
# Data mapping
# ---------------------------------------------------------------------------

def map_shopee_item_to_lead(item: dict, category: str, city: str) -> Lead:
    """
    Map an Apify Shopee scraper result item to our standard Lead format.

    The exact field names depend on the Apify actor used.  This handles
    common field patterns from popular Shopee scraper actors.
    """
    # Shop-level fields (try multiple key patterns)
    shop_name = (
        item.get("shopName")
        or item.get("shop_name")
        or item.get("seller", {}).get("shopName", "")
        or item.get("name", "")
    )

    shop_location = (
        item.get("shopLocation")
        or item.get("shop_location")
        or item.get("location", "")
        or item.get("seller", {}).get("shopLocation", "")
    )

    shop_url = (
        item.get("shopUrl")
        or item.get("shop_url")
        or item.get("url", "")
    )

    # Ratings / followers for notes
    rating = item.get("ratingAverage") or item.get("rating_star") or item.get("rating", "")
    followers = item.get("followerCount") or item.get("followers") or ""
    products = item.get("productCount") or item.get("totalProducts") or item.get("itemCount", "")
    response_rate = item.get("responseRate") or item.get("response_rate", "")

    notes_parts = []
    if rating:
        notes_parts.append(f"Rating: {rating}")
    if followers:
        notes_parts.append(f"Followers: {followers}")
    if products:
        notes_parts.append(f"Products: {products}")
    if response_rate:
        notes_parts.append(f"Response: {response_rate}")

    return Lead(
        business_name=str(shop_name).strip(),
        city=city or str(shop_location).strip(),
        category=category,
        website=str(shop_url).strip(),
        platform="shopee",
        notes=", ".join(notes_parts),
    )


def deduplicate_leads(leads: list[Lead]) -> list[Lead]:
    """Remove duplicate leads by business_name."""
    seen = set()
    unique = []
    for lead in leads:
        key = lead.business_name.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

CSV_FIELDNAMES = [
    "business_name", "contact_name", "email", "phone", "zalo",
    "website", "facebook", "platform", "city", "address",
    "category", "source", "score", "status", "notes", "scraped_date",
]


def save_csv(leads: list[Lead], category: str, city: str, output_dir: str) -> str:
    """Save leads to a CSV file matching the standard pipeline format."""
    os.makedirs(output_dir, exist_ok=True)

    city_slug = (city or "all").lower().replace(" ", "_")
    category_slug = category.lower().replace(" ", "_")
    today = date.today().isoformat()
    filename = f"shopee_{city_slug}_{category_slug}_{today}.csv"
    filepath = os.path.join(output_dir, filename)

    if not leads:
        logger.warning("No leads to save.")
        return filepath

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for lead in leads:
            writer.writerow(asdict(lead))

    logger.info(f"Saved {len(leads)} leads to {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Shopee Vietnam sellers by category using Apify"
    )
    parser.add_argument(
        "--category",
        required=True,
        help='Shopee category to search (e.g. "thoi trang nu", "my pham")',
    )
    parser.add_argument(
        "--city",
        default="",
        help='Filter by city (e.g. "Ho Chi Minh"). Optional.',
    )
    parser.add_argument(
        "--count",
        type=int,
        default=30,
        help="Max number of seller leads to collect (default: 30)",
    )
    parser.add_argument(
        "--output-dir",
        default="leads/data",
        help="Directory to save the output CSV (default: leads/data)",
    )
    parser.add_argument(
        "--actor-id",
        default=DEFAULT_ACTOR_ID,
        help=f"Apify actor ID to use (default: {DEFAULT_ACTOR_ID})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for Apify run (default: 300)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    token = get_apify_token()

    # Build the Apify actor input
    search_term = CATEGORY_KEYWORDS.get(args.category, args.category)
    location = CITY_TO_LOCATION.get(args.city, args.city) if args.city else ""

    run_input = {
        "searchKeyword": search_term,
        "country": "VN",
        "maxItems": args.count * 3,  # over-fetch to account for dedup
    }

    if location:
        run_input["location"] = location

    logger.info(f"Search: '{search_term}' | City: '{location or 'all'}' | Max items: {run_input['maxItems']}")

    # Start and wait for the Apify run
    run_id = start_actor_run(args.actor_id, token, run_input)
    run_data = wait_for_run(run_id, token, timeout=args.timeout)

    # Fetch results
    dataset_id = run_data["defaultDatasetId"]
    items = fetch_dataset_items(dataset_id, token)

    if not items:
        print("No results from Apify. Try different search terms.")
        sys.exit(1)

    # Map to Lead objects
    leads = [
        map_shopee_item_to_lead(item, args.category, args.city)
        for item in items
    ]

    # Deduplicate and limit
    leads = deduplicate_leads(leads)[:args.count]

    # Save to CSV
    output_path = save_csv(leads, args.category, args.city, args.output_dir)

    print(f"\nDone! {len(leads)} Shopee seller leads saved to: {output_path}")
    print("\nSample leads:")
    for lead in leads[:5]:
        print(f"  - {lead.business_name} | {lead.city} | {lead.website}")
        if lead.notes:
            print(f"    {lead.notes}")


if __name__ == "__main__":
    main()
