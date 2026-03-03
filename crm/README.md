# SEA Agency CRM — Google Sheets Setup Guide

## 1. Set Up Google Sheets API Credentials

### Step 1 — Create a Google Cloud Project
1. Open https://console.cloud.google.com
2. Click the project selector > **New Project** > name it `sea-automation-agency` > Create
3. Select the new project from the dropdown

### Step 2 — Enable the Google Sheets API
1. Go to **APIs & Services** > **Library**
2. Search "Google Sheets API" > Click it > **Enable**

### Step 3 — Create a Service Account
1. **APIs & Services** > **Credentials** > **Create Credentials** > **Service account**
2. Name it `crm-bot`, set role = **Editor** > Done

### Step 4 — Download the JSON Key
1. Click the service account you just created
2. **Keys** tab > **Add Key** > **Create new key** > **JSON**
3. Save the downloaded file as:
   ```
   ~/sea-automation-agency/credentials.json
   ```
4. **Important:** Never commit this file to GitHub. It's in .gitignore.

---

## 2. Install Dependencies

```bash
pip install google-auth google-api-python-client python-dotenv
```

---

## 3. Run First-Time Setup

```bash
cd ~/sea-automation-agency/crm
python setup_crm.py
```

This will:
- Create a new Google Spreadsheet called **"SEA Agency CRM"**
- Build all 5 tabs: Leads, Outreach Tracker, Proposals, Clients, Revenue
- Format headers with color coding and bold text
- Add dropdown validation for Status fields
- Save the spreadsheet ID to `~/sea-automation-agency/.env`

Open the printed URL to see your new CRM.

---

## 4. Daily Usage

### Add a new lead
```bash
python crm/add_lead.py \
  --name "Shop Thời Trang ABC" \
  --contact "Nguyễn Văn A" \
  --email "contact@shopABC.vn" \
  --phone "0901234567" \
  --platform "Shopee,TikTok Shop" \
  --city "Ho Chi Minh" \
  --monthly-orders 600 \
  --pain-point "Manual order entry across platforms" \
  --score 8
```

### Update a lead's status
```bash
python crm/update_status.py \
  --business-name "Shop Thời Trang ABC" \
  --status "Contacted" \
  --notes "Sent email 1 on 2025-03-03"
```

### View the pipeline dashboard
```bash
python crm/pipeline_report.py
```

---

## 5. Skill Integration

| Skill | CRM Action |
|-------|-----------|
| `/find-leads` | Run `add_lead.py` for each lead found |
| `/outreach` | Run `update_status.py` after each email sent |
| `/propose` | Manually add row to Proposals tab |
| `/deliver` | Update client to Active in Clients tab |
| `/report` | Update Next Report Due date in Clients tab |
| `/pipeline` | Reads `pipeline_report.py` output |

---

## 6. CRM Sheet Structure

**Leads tab** — Status options: New → Contacted → Replied → Meeting → Proposal Sent → Closed Won → Closed Lost

**Outreach Tracker tab** — Tracks exactly which emails were sent and when, drives follow-up logic

**Proposals tab** — Status options: Draft → Sent → Negotiating → Won → Lost

**Clients tab** — Active client roster with health scores and report schedules

**Revenue tab** — Monthly MRR tracking and growth metrics
