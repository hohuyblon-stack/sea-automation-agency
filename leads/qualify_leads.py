#!/usr/bin/env python3
"""
qualify_leads.py - Score and filter raw leads from scrapers.

Reads a CSV of raw leads, applies a scoring model, and outputs a filtered
CSV of qualified leads ready for outreach.

Usage:
    python qualify_leads.py --input leads/data/hcm_shop_thoi_trang_2026-03-03.csv
    python qualify_leads.py --input leads/data/raw.csv --min-score 40 --output leads/data/qualified.csv

Scoring model (100 points max):
    +30  Has phone number
    +20  Has email address
    +20  Platform detected (Shopee/TikTok/Lazada)
    +15  City is a major market (HCM, Hanoi, Danang)
    +10  Has website
    +5   Seller keyword density score

Outputs:
    - Filtered CSV with score column populated
    - Summary printed to stdout
"""

import argparse
import csv
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 30
MAJOR_CITIES = {
    "ho chi minh", "hcm", "tphcm", "saigon", "hồ chí minh",
    "ha noi", "hanoi", "hà nội",
    "da nang", "danang", "đà nẵng",
    "can tho", "cần thơ",
    "hai phong", "hải phòng",
    "bien hoa", "biên hòa",
}

ECOM_PLATFORMS = {"shopee", "tiktok", "tiktok_shop", "lazada", "sendo", "tiki"}

SELLER_KEYWORDS = [
    "shop", "cửa hàng", "bán", "order", "inbox", "đặt hàng",
    "ship", "cod", "freeship", "đơn hàng", "kho", "sỉ", "lẻ",
]

DISQUALIFY_PATTERNS = [
    r"@gmail\.com$",           # generic Gmail with no business name
    r"test",
    r"example",
    r"demo",
    r"unknown",
]


@dataclass
class ScoredLead:
    business_name: str
    contact_name: str
    email: str
    phone: str
    zalo: str = ""
    website: str = ""
    facebook: str = ""
    facebook_profile: str = ""
    platform: str = ""
    city: str = ""
    address: str = ""
    category: str = ""
    source: str = ""
    score: int = 0
    status: str = "new"
    notes: str = ""
    scraped_date: str = ""
    post_text: str = ""
    post_url: str = ""
    group_name: str = ""
    qualify_reason: str = ""


def score_lead(row: dict) -> tuple[int, str]:
    """
    Score a raw lead row. Returns (score, reason_string).
    """
    score = 0
    reasons = []

    phone = row.get("phone", "").strip()
    email = row.get("email", "").strip()
    platform = row.get("platform", "").strip().lower()
    city = row.get("city", "").strip().lower()
    website = row.get("website", "").strip()
    business_name = row.get("business_name", "").strip()
    post_text = row.get("post_text", "").strip().lower()
    existing_score = int(row.get("score", 0) or 0)

    # Phone number
    if phone and len(re.sub(r"\D", "", phone)) >= 10:
        score += 30
        reasons.append("has_phone")

    # Email address
    if email and "@" in email:
        score += 20
        reasons.append("has_email")

    # Platform detected
    detected_platforms = [p.strip() for p in platform.split(",") if p.strip()]
    if any(p in ECOM_PLATFORMS for p in detected_platforms):
        score += 20
        reasons.append(f"platform:{platform}")

    # Major city
    if any(c in city for c in MAJOR_CITIES):
        score += 15
        reasons.append(f"major_city:{city}")

    # Has website
    if website:
        score += 10
        reasons.append("has_website")

    # Keyword density in post text
    if post_text:
        kw_hits = sum(1 for kw in SELLER_KEYWORDS if kw in post_text)
        kw_score = min(kw_hits * 2, 5)
        if kw_score > 0:
            score += kw_score
            reasons.append(f"keywords:{kw_hits}")

    # Carry forward any existing score from scraper (up to 5 bonus points)
    if existing_score > 0:
        bonus = min(existing_score // 20, 5)
        score += bonus

    return min(score, 100), ", ".join(reasons)


def is_disqualified(row: dict) -> Optional[str]:
    """Return a disqualification reason if the lead should be rejected."""
    business_name = row.get("business_name", "").strip().lower()
    email = row.get("email", "").strip().lower()
    phone = row.get("phone", "").strip()

    # No meaningful contact info at all
    if not phone and not email:
        return "no_contact_info"

    # Disqualify known junk patterns
    for pattern in DISQUALIFY_PATTERNS:
        if business_name and re.search(pattern, business_name, re.IGNORECASE):
            return f"junk_name:{business_name}"
        if email and re.search(pattern, email, re.IGNORECASE):
            return f"junk_email:{email}"

    # Status already closed
    status = row.get("status", "").strip().lower()
    if status in {"closed lost", "disqualified", "do not contact"}:
        return f"status:{status}"

    return None


def load_csv(filepath: str) -> List[dict]:
    """Load a CSV file and return list of row dicts."""
    path = Path(filepath)
    if not path.exists():
        logger.error(f"Input file not found: {filepath}")
        sys.exit(1)

    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    logger.info(f"Loaded {len(rows)} rows from {filepath}")
    return rows


def save_csv(leads: List[ScoredLead], filepath: str):
    """Save qualified leads to CSV."""
    if not leads:
        logger.warning("No qualified leads to save.")
        return

    os.makedirs(Path(filepath).parent, exist_ok=True)

    fieldnames = [
        "business_name", "contact_name", "email", "phone", "zalo",
        "website", "facebook", "platform", "city", "address",
        "category", "source", "score", "status", "notes",
        "scraped_date", "qualify_reason",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow(asdict(lead))

    logger.info(f"Saved {len(leads)} qualified leads to {filepath}")


def qualify(
    input_path: str,
    output_path: str,
    min_score: int = DEFAULT_MIN_SCORE,
    verbose: bool = False,
) -> List[ScoredLead]:
    """Main qualification pipeline."""
    rows = load_csv(input_path)

    qualified = []
    disqualified_count = 0
    low_score_count = 0

    for row in rows:
        # Check hard disqualifiers first
        disq_reason = is_disqualified(row)
        if disq_reason:
            disqualified_count += 1
            if verbose:
                logger.debug(f"Disqualified '{row.get('business_name')}': {disq_reason}")
            continue

        # Score the lead
        score, reason = score_lead(row)

        if score < min_score:
            low_score_count += 1
            if verbose:
                logger.debug(f"Low score ({score}) for '{row.get('business_name')}': {reason}")
            continue

        # Build ScoredLead
        lead = ScoredLead(
            business_name=row.get("business_name", ""),
            contact_name=row.get("contact_name", ""),
            email=row.get("email", ""),
            phone=row.get("phone", ""),
            zalo=row.get("zalo", ""),
            website=row.get("website", ""),
            facebook=row.get("facebook", "") or row.get("facebook_profile", ""),
            platform=row.get("platform", ""),
            city=row.get("city", ""),
            address=row.get("address", ""),
            category=row.get("category", ""),
            source=row.get("source", ""),
            score=score,
            status="new",
            notes=row.get("notes", ""),
            scraped_date=row.get("scraped_date", str(date.today())),
            qualify_reason=reason,
        )
        qualified.append(lead)

    # Sort by score descending
    qualified.sort(key=lambda l: l.score, reverse=True)

    save_csv(qualified, output_path)

    # Print summary
    total = len(rows)
    print(f"\n{'='*50}")
    print(f"Lead Qualification Summary")
    print(f"{'='*50}")
    print(f"Total raw leads:      {total}")
    print(f"Disqualified:         {disqualified_count}")
    print(f"Low score (<{min_score}):     {low_score_count}")
    print(f"Qualified leads:      {len(qualified)}")
    print(f"Output:               {output_path}")
    if qualified:
        scores = [l.score for l in qualified]
        print(f"Score range:          {min(scores)}–{max(scores)}")
        print(f"Average score:        {sum(scores)/len(scores):.1f}")
        print(f"\nTop 5 leads:")
        for lead in qualified[:5]:
            print(f"  [{lead.score}] {lead.business_name} | {lead.phone} | {lead.platform} | {lead.city}")
    print(f"{'='*50}\n")

    return qualified


def main():
    parser = argparse.ArgumentParser(
        description="Score and filter raw leads for outreach"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to raw leads CSV from scraper"
    )
    parser.add_argument(
        "--output", default="",
        help="Output path for qualified leads CSV (default: input_dir/qualified_YYYY-MM-DD.csv)"
    )
    parser.add_argument(
        "--min-score", type=int, default=DEFAULT_MIN_SCORE,
        help=f"Minimum score to qualify (default: {DEFAULT_MIN_SCORE})"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show why each lead was disqualified"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_path = args.output
    if not output_path:
        input_dir = Path(args.input).parent
        today = date.today().isoformat()
        output_path = str(input_dir / f"qualified_{today}.csv")

    qualify(
        input_path=args.input,
        output_path=output_path,
        min_score=args.min_score,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
