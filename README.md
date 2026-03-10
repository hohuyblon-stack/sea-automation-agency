# SEA Automation Agency — Claude Code Powered

A production-ready B2B automation agency system built on Claude Code, targeting Vietnamese e-commerce sellers on Shopee, TikTok Shop, and Lazada. This system automates every stage of the agency pipeline — from finding leads to delivering services and reporting results.

---

## What This System Is

This is not a template. It is a fully operational agency pipeline where Claude Code skills drive each stage of the business. The system handles:

- **Lead Generation** — scraping Google Maps and Facebook groups for e-commerce sellers
- **Outreach** — sending personalized email sequences in Vietnamese and English
- **Proposal Creation** — generating professional, client-ready proposals from templates
- **Service Delivery** — deploying automation scripts for order sync, inventory alerts, and reporting
- **Client Reporting** — auto-generating monthly HTML/PDF reports with metrics and recommendations

The target client is a Vietnamese e-commerce seller doing 200–2,000 orders per month across Shopee, TikTok Shop, or Lazada who is managing everything manually and is ready to automate.

---

## The 5-Stage Pipeline

```
FIND → OUTREACH → PROPOSE → DELIVER → REPORT
```

### Stage 1: FIND
Identify qualified leads using scrapers targeting Google Maps business listings and Facebook group posts. Leads are scored and filtered before entering the outreach sequence.

### Stage 2: OUTREACH
A 3-email sequence (Day 1, Day 4, Day 10) is sent via Gmail API. All emails are written in Vietnamese first, with English variants. The sequence is tracked to avoid duplicates.

### Stage 3: PROPOSE
When a lead responds, a tailored proposal is generated from a template by filling in client-specific data. Output is both Markdown and HTML.

### Stage 4: DELIVER
Once signed, the client's automation is deployed using one of the service delivery templates (order sync, inventory alerts, reporting dashboard). Each client gets their own directory with their config and data.

### Stage 5: REPORT
Every month, a professional HTML/PDF report is generated and emailed to the client showing automations run, time saved, orders processed, and recommendations.

---

## Quick Start

### 1. Clone and Set Up

```bash
cd ~/sea-automation-agency
bash scripts/setup.sh
source venv/bin/activate
```

### 2. Configure the Agency

```bash
cp .env.example .env
# Edit .env with your Gmail credentials, Zalo webhook, etc.
# Edit config.yaml: fill in sender_name and sender_email
```

### 3. Set Up Google API Auth (no gcloud CLI needed)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or select an existing one)
3. Enable these APIs: **Gmail API**, **Google Sheets API**, **Google Drive API**
4. Go to **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID**
5. Choose **Desktop app** as the application type
6. Download the JSON file and save it as `credentials.json` in the project root
7. Run the auth setup script:

```bash
python scripts/auth_setup.py
```

This opens a browser window for Google sign-in and saves your token locally. No `gcloud` CLI or external tools required.

To verify everything works:

```bash
python scripts/auth_setup.py --test
```

To re-authenticate (e.g., after changing scopes):

```bash
python scripts/auth_setup.py --reauth
```

### 4. Find Your First Leads

```bash
python leads/scrapers/google_maps_leads.py \
  --category "shop quan ao" \
  --city "Ho Chi Minh" \
  --count 30
```

### 5. Qualify the Leads

```bash
python leads/qualify_leads.py \
  --input leads/data/ho_chi_minh_shop_quan_ao_2026-03-03.csv \
  --output leads/data/qualified_leads.csv
```

### 6. Send Outreach Sequence

```bash
# Dry run first
python outreach/send_sequence.py --dry-run

# Send for real
python outreach/send_sequence.py --input leads/data/qualified_leads.csv
```

### 7. Generate a Proposal

```bash
python proposals/generate_proposal.py \
  --template proposals/templates/order_sync_proposal.md \
  --client-data '{"client_name":"Nguyen Van A","business_name":"Shop Thoi Trang A","platform":"Shopee","monthly_orders":"500","pain_point":"quan ly don hang thu cong mat nhieu gio"}' \
  --output-dir generated/
```

### 8. Deploy a Service

```bash
# Copy the template for a new client
cp -r delivery/templates/order_sync clients/shop_thoi_trang_a/
# Edit clients/shop_thoi_trang_a/config.json with real credentials
python clients/shop_thoi_trang_a/main.py
```

### 9. Generate Monthly Report

```bash
python reports/generate_monthly_report.py \
  --client-name "shop_thoi_trang_a" \
  --month 2026-03
```

---

## Directory Structure

```
sea-automation-agency/
├── README.md                          # This file
├── config.yaml                        # Agency-wide configuration
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment variable template
├── .gitignore
│
├── leads/
│   ├── README.md                      # Lead storage documentation
│   ├── qualify_leads.py               # Lead scoring script
│   ├── data/                          # Raw and qualified CSV files (gitignored)
│   └── scrapers/
│       ├── google_maps_leads.py       # Google Maps business scraper
│       └── facebook_group_leads.py    # Facebook group lead extractor
│
├── outreach/
│   └── templates/
│       ├── email_1_cold_vi.md         # Day 1 cold email (Vietnamese)
│       ├── email_1_cold_en.md         # Day 1 cold email (English)
│       ├── email_2_followup_vi.md     # Day 4 follow-up (Vietnamese)
│       ├── email_2_followup_en.md     # Day 4 follow-up (English)
│       ├── email_3_breakup_vi.md      # Day 10 final email (Vietnamese)
│       └── email_3_breakup_en.md     # Day 10 final email (English)
│   └── send_sequence.py               # Gmail sequence sender
│
├── proposals/
│   ├── generate_proposal.py           # Proposal generator script
│   └── templates/
│       └── order_sync_proposal.md     # Full proposal template (VI + EN)
│
├── delivery/
│   └── templates/
│       ├── order_sync/
│       │   ├── README.md              # Setup guide
│       │   ├── main.py                # Order sync daemon
│       │   └── config.json            # Template config
│       ├── inventory_alerts/
│       │   └── main.py                # Inventory alert daemon
│       └── reporting_dashboard/
│           └── main.py                # Weekly/monthly report generator
│
├── clients/                           # One folder per client (gitignored private data)
│   └── README.md
│
├── reports/
│   ├── generate_monthly_report.py     # Monthly report generator
│   └── output/                        # Generated reports
│
├── scripts/
│   └── setup.sh                       # First-run setup script
│
└── generated/                         # Generated proposals and docs
```

---

## Claude Code Skills

Use these slash commands to run agency operations:

| Skill | What It Does |
|-------|-------------|
| `/find-leads` | Runs the scrapers and qualify pipeline to generate a fresh lead list |
| `/outreach` | Sends or previews the next email in the sequence for pending leads |
| `/propose` | Generates a tailored proposal for a specific lead |
| `/deliver` | Sets up a new client delivery folder from a service template |
| `/report` | Generates and emails the monthly report for a client |

To invoke, type the skill name in Claude Code with any required arguments, for example:

```
/find-leads --city "Ha Noi" --category "shop my pham" --count 50
/outreach --dry-run
/propose --client "Nguyen Thi B" --service order_sync
/deliver --client "shop_dep_xinh" --service inventory_alerts
/report --client "shop_thoi_trang_a" --month 2026-03
```

---

## Target Market

**Who:** Vietnamese e-commerce sellers operating on Shopee, TikTok Shop, or Lazada

**Company size:** 1–50 employees (solo sellers to small teams)

**Revenue range:** 500M–10B VND annually (~$20K–$400K USD)

**Pain points:**
- Managing orders manually across 2–3 platforms (hours wasted daily)
- No inventory visibility — overselling and stockouts
- No reporting — decisions made by gut, not data
- No time for marketing — too busy with operations

**Services offered:**

| Service | Price (VND) | Price (USD) | Delivery |
|---------|-------------|-------------|----------|
| Multi-Platform Order Sync | 15,000,000 | $600 | 7 days |
| Inventory Alert System | 8,000,000 | $320 | 5 days |
| Automated Reporting Dashboard | 12,000,000 | $480 | 7 days |
| Lead Capture + Auto Follow-up | 10,000,000 | $400 | 5 days |
| Full Business Automation Package | 45,000,000 | $1,800 | 21 days |

---

## Notes

- All outreach emails default to Vietnamese. English templates are available for cross-border or bilingual clients.
- Gmail API requires an approved OAuth app or a personal account with `credentials.json` set up.
- The Shopee API integration in `delivery/templates/order_sync/main.py` uses the official Shopee Open Platform API. You will need to register as a partner at [open.shopee.com](https://open.shopee.com).
- Zalo notifications use webhook URLs — configure yours in `.env`.
- Never commit `credentials.json`, `token.json`, or `.env` to version control.
