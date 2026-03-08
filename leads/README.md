# Leads Directory

This directory contains all lead generation scripts and raw lead data for the SEA Automation Agency.

---

## Directory Structure

```
leads/
├── README.md                       # This file
├── qualify_leads.py                # Scores and filters raw leads
├── data/                           # CSV files (gitignored — may contain PII)
│   ├── raw/                        # Raw output from scrapers
│   └── qualified_leads.csv         # Scored + filtered leads ready for outreach
└── scrapers/
    ├── google_maps_leads.py        # Scrapes Google Maps business listings
    ├── facebook_group_leads.py     # Extracts leads from Facebook group posts
    ├── shopee_category_leads.py    # Scrapes Shopee sellers via Apify API
    └── hunter_enrichment.py        # Enriches leads with emails via Hunter.io
```

---

## CSV Format

All lead CSV files use the following column structure:

| Column | Description | Example |
|--------|-------------|---------|
| `business_name` | Name of the business | Shop Thoi Trang Minh Anh |
| `contact_name` | Owner or manager name (if found) | Nguyen Minh Anh |
| `email` | Business email | minhanh.shop@gmail.com |
| `phone` | Vietnamese phone number | 0901234567 |
| `zalo` | Zalo ID (often same as phone) | 0901234567 |
| `website` | Website URL if available | https://shopminh.vn |
| `facebook` | Facebook page URL | https://facebook.com/shopminh |
| `platform` | e-commerce platform(s) | shopee, tiktok_shop |
| `city` | City/province | Ho Chi Minh |
| `address` | Full address | 123 Nguyen Trai, Q1, HCM |
| `category` | Business category | shop quan ao |
| `source` | Where lead was found | google_maps, shopee_category, facebook_group |
| `score` | Qualification score 1–10 | 7 |
| `status` | Pipeline status | new / contacted / replied / proposed / closed |
| `notes` | Any additional notes | Sells on Shopee and TikTok |
| `scraped_date` | When the lead was found | 2026-03-03 |

---

## Lead Statuses

| Status | Meaning |
|--------|---------|
| `new` | Just scraped, not yet contacted |
| `qualified` | Passed scoring threshold (score >= 4) |
| `contacted` | Day 1 email sent |
| `follow_up_1` | Day 4 follow-up sent |
| `follow_up_2` | Day 10 final email sent |
| `replied` | Lead responded — move to proposal stage |
| `proposed` | Proposal sent |
| `negotiating` | In discussion |
| `closed_won` | Signed and paid |
| `closed_lost` | Not interested |
| `not_qualified` | Scored below threshold |

---

## How to Use the /find-leads Skill

The `/find-leads` skill orchestrates the full scraping + qualification pipeline in one command.

### Basic Usage

```bash
/find-leads --city "Ho Chi Minh" --category "shop thoi trang" --count 30
```

### What It Does

1. Runs `leads/scrapers/google_maps_leads.py` to scrape businesses
2. Optionally runs `leads/scrapers/facebook_group_leads.py` if `--facebook-group` is specified
3. Merges results into a single raw CSV
4. Runs `leads/qualify_leads.py` to score and filter
5. Outputs `leads/data/qualified_leads.csv` ready for outreach

### Full Options

```bash
/find-leads \
  --city "Ha Noi" \
  --category "shop my pham" \
  --count 50 \
  --facebook-group "https://facebook.com/groups/shopee-sellers-vn" \
  --min-score 5
```

### Running Scrapers Directly

```bash
# Google Maps
python leads/scrapers/google_maps_leads.py \
  --category "shop thoi trang" \
  --city "Ho Chi Minh" \
  --count 20

# Shopee Category (via Apify — requires APIFY_API_TOKEN in .env)
python leads/scrapers/shopee_category_leads.py \
  --category "thoi trang nu" \
  --city "Ho Chi Minh" \
  --count 30

# Facebook Groups (requires manual setup — see script docstring)
python leads/scrapers/facebook_group_leads.py \
  --group-url "https://facebook.com/groups/123456" \
  --count 50

# Enrich leads with emails (requires HUNTER_API_KEY in .env)
python leads/scrapers/hunter_enrichment.py \
  --input leads/data/shopee_ho_chi_minh_thoi_trang_2026-03-06.csv \
  --output leads/data/enriched_leads.csv

# Dry-run email enrichment (preview without API calls)
python leads/scrapers/hunter_enrichment.py \
  --input leads/data/leads.csv \
  --dry-run

# Qualify leads
python leads/qualify_leads.py \
  --input leads/data/ho_chi_minh_shop_thoi_trang_2026-03-03.csv \
  --output leads/data/qualified_leads.csv \
  --min-score 4
```

---

## Privacy Note

The `leads/data/` directory is gitignored. Raw lead data contains personal contact information and should not be committed to version control. Always handle lead data responsibly and in compliance with Vietnamese data protection laws and platform terms of service.

---

## Adding New Lead Sources

To add a new scraper:
1. Create a new file in `leads/scrapers/`
2. Output CSV must match the column format defined above
3. Pass the output to `qualify_leads.py` for scoring
4. Update this README with the new source
