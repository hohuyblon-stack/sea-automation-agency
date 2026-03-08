#!/usr/bin/env python3
"""
Hunter.io Email Enrichment
============================
Takes a CSV file with a 'website' column, queries Hunter.io's Domain Search
API to find verified email addresses, and appends them to the CSV.

Requirements:
    pip install requests python-dotenv

Environment:
    HUNTER_API_KEY  — your Hunter.io API key (set in .env)

Usage:
    python leads/scrapers/hunter_enrichment.py \
        --input leads/data/shopee_ho_chi_minh_thoi_trang_2026-03-06.csv \
        --output leads/data/enriched_leads.csv

    # Dry-run to preview what would be enriched
    python leads/scrapers/hunter_enrichment.py \
        --input leads/data/raw_leads.csv \
        --dry-run

    # Only enrich leads missing emails
    python leads/scrapers/hunter_enrichment.py \
        --input leads/data/leads.csv \
        --skip-existing
"""

import argparse
import csv
import logging
import os
import sys
import time
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
# Hunter.io configuration
# ---------------------------------------------------------------------------

HUNTER_BASE_URL = "https://api.hunter.io/v2"

# Standard CSV fieldnames (matching the rest of the pipeline)
CSV_FIELDNAMES = [
    "business_name", "contact_name", "email", "phone", "zalo",
    "website", "facebook", "platform", "city", "address",
    "category", "source", "score", "status", "notes", "scraped_date",
]


# ---------------------------------------------------------------------------
# Hunter.io API helpers
# ---------------------------------------------------------------------------

def get_hunter_api_key() -> str:
    """Load Hunter.io API key from .env or environment."""
    env = dotenv_values()
    key = env.get("HUNTER_API_KEY") or os.environ.get("HUNTER_API_KEY", "")
    if not key:
        logger.error(
            "HUNTER_API_KEY not found.  Set it in .env or as an environment variable."
        )
        sys.exit(1)
    return key


def extract_domain(url: str) -> str:
    """
    Extract the domain from a URL for Hunter.io lookup.

    Examples:
        https://shopminh.vn/products  ->  shopminh.vn
        http://www.example.com        ->  example.com
        shopee.vn/shop/12345          ->  (skip — marketplace domain)
    """
    if not url or not url.strip():
        return ""

    url = url.strip().lower()

    # Remove protocol
    for prefix in ("https://", "http://", "//"):
        if url.startswith(prefix):
            url = url[len(prefix):]

    # Remove www.
    if url.startswith("www."):
        url = url[4:]

    # Take just the domain part
    domain = url.split("/")[0].split("?")[0].split("#")[0]

    # Skip marketplace domains — Hunter.io won't find individual seller emails
    skip_domains = {
        "shopee.vn", "shopee.com", "lazada.vn", "lazada.com",
        "tiktok.com", "facebook.com", "fb.com", "instagram.com",
        "zalo.me", "google.com", "youtube.com",
    }
    if domain in skip_domains:
        return ""

    # Must have at least one dot to be a valid domain
    if "." not in domain:
        return ""

    return domain


def domain_search(api_key: str, domain: str) -> dict:
    """
    Call Hunter.io Domain Search API.

    Returns dict with:
        - emails: list of email dicts (value, type, confidence, first_name, last_name)
        - organization: str
        - pattern: str (e.g. "{first}.{last}")
    """
    url = f"{HUNTER_BASE_URL}/domain-search"
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": 5,  # We only need the best match
    }

    try:
        resp = requests.get(url, params=params, timeout=15)

        # Rate limited
        if resp.status_code == 429:
            logger.warning("Hunter.io rate limit hit. Waiting 10s ...")
            time.sleep(10)
            resp = requests.get(url, params=params, timeout=15)

        if resp.status_code == 401:
            logger.error("Hunter.io API key is invalid or expired.")
            sys.exit(1)

        if resp.status_code == 404 or resp.status_code == 400:
            # Domain not found or invalid
            return {"emails": [], "organization": "", "pattern": ""}

        resp.raise_for_status()
        return resp.json().get("data", {})

    except requests.RequestException as e:
        logger.warning(f"Hunter.io request failed for {domain}: {e}")
        return {"emails": [], "organization": "", "pattern": ""}


def email_verifier(api_key: str, email: str) -> dict:
    """
    Verify a single email address via Hunter.io Email Verifier API.

    Returns dict with: status (valid/invalid/accept_all/unknown), score, etc.
    """
    url = f"{HUNTER_BASE_URL}/email-verifier"
    params = {"email": email, "api_key": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            time.sleep(10)
            resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except requests.RequestException as e:
        logger.warning(f"Verification failed for {email}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Enrichment logic
# ---------------------------------------------------------------------------

def pick_best_email(emails: list[dict]) -> tuple[str, str]:
    """
    From Hunter.io results, pick the best email.

    Returns (email_address, contact_name).
    Prefers: personal > generic, higher confidence first.
    """
    if not emails:
        return "", ""

    # Sort by confidence desc, prefer personal emails
    scored = []
    for e in emails:
        email = e.get("value", "")
        confidence = e.get("confidence", 0) or 0
        email_type = e.get("type", "generic")
        first = e.get("first_name", "") or ""
        last = e.get("last_name", "") or ""

        # Bonus for personal emails
        type_bonus = 50 if email_type == "personal" else 0
        total_score = confidence + type_bonus

        name = f"{first} {last}".strip()
        scored.append((total_score, email, name))

    scored.sort(reverse=True)
    _, best_email, best_name = scored[0]
    return best_email, best_name


def enrich_leads(
    input_path: str,
    output_path: str,
    api_key: str,
    skip_existing: bool = True,
    dry_run: bool = False,
    verify: bool = False,
    rate_limit_delay: float = 1.5,
) -> dict:
    """
    Read a CSV, enrich leads with Hunter.io emails, write enriched CSV.

    Returns stats dict with counts.
    """
    # Read input CSV
    leads = []
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(row)

    if not leads:
        logger.warning(f"No leads found in {input_path}")
        return {"total": 0, "enriched": 0, "skipped": 0, "no_domain": 0}

    logger.info(f"Loaded {len(leads)} leads from {input_path}")

    stats = {"total": len(leads), "enriched": 0, "skipped": 0, "no_domain": 0, "verified": 0}

    for i, lead in enumerate(leads):
        website = lead.get("website", "")
        existing_email = lead.get("email", "").strip()

        # Skip if already has email and flag is set
        if skip_existing and existing_email:
            logger.debug(f"  [{i+1}/{len(leads)}] SKIP {lead.get('business_name', '?')} — already has email")
            stats["skipped"] += 1
            continue

        # Extract domain
        domain = extract_domain(website)
        if not domain:
            logger.debug(f"  [{i+1}/{len(leads)}] SKIP {lead.get('business_name', '?')} — no usable domain")
            stats["no_domain"] += 1
            continue

        if dry_run:
            logger.info(f"  [{i+1}/{len(leads)}] DRY-RUN: would query {domain} for {lead.get('business_name', '?')}")
            continue

        # Query Hunter.io
        logger.info(f"  [{i+1}/{len(leads)}] Querying {domain} ...")
        result = domain_search(api_key, domain)
        emails = result.get("emails", [])
        best_email, contact_name = pick_best_email(emails)

        if best_email:
            lead["email"] = best_email
            if contact_name and not lead.get("contact_name", "").strip():
                lead["contact_name"] = contact_name

            # Append note
            org = result.get("organization", "")
            existing_notes = lead.get("notes", "")
            enrichment_note = f"Email from Hunter.io (domain: {domain})"
            if org:
                enrichment_note += f", Org: {org}"
            lead["notes"] = f"{existing_notes}, {enrichment_note}".strip(", ")

            stats["enriched"] += 1
            logger.info(f"    ✅ Found: {best_email} ({contact_name or 'no name'})")

            # Optional verification
            if verify:
                v = email_verifier(api_key, best_email)
                v_status = v.get("status", "unknown")
                v_score = v.get("score", 0)
                logger.info(f"    📧 Verified: {v_status} (score: {v_score})")
                if v_status == "valid":
                    stats["verified"] += 1
        else:
            logger.info(f"    ❌ No emails found for {domain}")

        # Rate limit
        time.sleep(rate_limit_delay)

    # Write output CSV
    if not dry_run:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Ensure all fieldnames are present
        fieldnames = CSV_FIELDNAMES.copy()
        for lead in leads:
            for key in lead:
                if key not in fieldnames:
                    fieldnames.append(key)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead)

        logger.info(f"Saved enriched leads to {output_path}")

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Enrich lead CSV with verified emails from Hunter.io"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV file with a 'website' column",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Path for enriched output CSV (default: input with _enriched suffix)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip leads that already have an email (default: true)",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-enrich all leads, even those with emails",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify found emails via Hunter.io Email Verifier (uses extra API credits)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which leads would be enriched without making API calls",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between API calls (default: 1.5)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    # Default output path
    output = args.output
    if not output:
        base, ext = os.path.splitext(args.input)
        output = f"{base}_enriched{ext}"

    skip = not args.no_skip

    if args.dry_run:
        print(f"\n🔍 DRY RUN — previewing enrichment for: {args.input}\n")
    else:
        api_key = get_hunter_api_key()

    stats = enrich_leads(
        input_path=args.input,
        output_path=output,
        api_key="" if args.dry_run else api_key,
        skip_existing=skip,
        dry_run=args.dry_run,
        verify=args.verify,
        rate_limit_delay=args.delay,
    )

    print(f"\n{'='*50}")
    print(f"Enrichment Results")
    print(f"{'='*50}")
    print(f"  Total leads:   {stats['total']}")
    print(f"  Enriched:      {stats['enriched']}")
    print(f"  Skipped:       {stats['skipped']} (already had email)")
    print(f"  No domain:     {stats['no_domain']} (no usable website)")
    if stats.get("verified"):
        print(f"  Verified:      {stats['verified']}")
    if not args.dry_run:
        print(f"\n  Output: {output}")
    print()


if __name__ == "__main__":
    main()
