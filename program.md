# SEA Automation Agency — Program Rules
# (Karpathy's Autoresearch Pattern: Human writes the rules, AI loops until met)
#
# Each pipeline stage defines:
#   - RULES: Hard constraints (must pass)
#   - METRICS: Measurable quality scores (0-100)
#   - THRESHOLD: Minimum score to pass without re-iteration
#   - MAX_ITERATIONS: Safety cap on agent loop retries

---

## Stage 1: FIND (Lead Generation + Qualification)

### Rules
- Every qualified lead MUST have at least one contact method (phone or email)
- No junk/test entries (test, example, demo, unknown patterns → reject)
- Leads marked "Closed Lost" or "Disqualified" are never re-qualified
- Duplicate business names within the same batch are merged, not double-counted
- Phone numbers must have ≥10 digits after stripping non-numeric chars

### Metrics
- **contact_coverage**: % of qualified leads with BOTH phone AND email (target: ≥60%)
- **platform_match**: % of qualified leads with a detected e-commerce platform (target: ≥70%)
- **city_concentration**: % of leads in major cities (target: ≥50%)
- **avg_score**: Average qualification score of output batch (target: ≥45)
- **yield_rate**: qualified / total raw leads (target: ≥25%)

### Threshold: 70
### Max Iterations: 3

### Improvement Actions
- If contact_coverage < 60%: broaden scraper search terms, try alternate contact fields
- If platform_match < 70%: add platform detection heuristics (check website/social for Shopee/TikTok links)
- If yield_rate < 25%: lower min_score by 5, or expand city list
- If avg_score < 45: tighten scraper targeting to higher-signal sources

---

## Stage 2: OUTREACH (Email Sequence)

### Rules
- Never send to a lead that has replied or booked a meeting
- Respect sequence timing: Email 2 at day 4+, Email 3 at day 10+
- All {{variables}} must be fully resolved (no raw placeholders in sent email)
- Rate limit: max 50 emails per hour, 200 per day
- Every send must be logged in CRM (Outreach Tracker sheet)

### Metrics
- **delivery_rate**: % of emails successfully sent (no API errors) (target: ≥95%)
- **personalization_score**: % of emails with all 5 core variables filled (target: 100%)
- **sequence_compliance**: % of sends that respect timing rules (target: 100%)
- **template_render_clean**: % of emails with zero unresolved {{placeholders}} (target: 100%)
- **crm_sync_rate**: % of sends tracked in CRM within 1 minute (target: ≥98%)

### Threshold: 90
### Max Iterations: 2

### Improvement Actions
- If delivery_rate < 95%: check Gmail API quota, retry failed sends with backoff
- If personalization_score < 100%: flag leads with missing fields, skip or fill defaults
- If template_render_clean < 100%: audit template variables vs lead CSV columns
- If crm_sync_rate < 98%: add retry logic to Sheets API calls

---

## Stage 3: PROPOSE (Proposal Generation)

### Rules
- Proposal must include: client name, business name, platform, pricing, ROI estimate
- All monetary values formatted correctly (VND with dots, USD with commas)
- Generated proposal file must be valid Markdown AND valid HTML
- ROI calculation: hours_saved = (monthly_orders × 5min) / 60
- Proposal ID format: SEA-YYYYMMDD-SLUG

### Metrics
- **field_completeness**: % of required fields populated (target: 100%)
- **format_validity**: passes Markdown + HTML lint (target: 100%)
- **roi_accuracy**: ROI math is internally consistent (target: 100%)
- **file_output**: both .md and .html generated successfully (target: 100%)

### Threshold: 95
### Max Iterations: 2

### Improvement Actions
- If field_completeness < 100%: prompt for missing data or use smart defaults
- If format_validity < 100%: fix template syntax errors, re-render
- If roi_accuracy < 100%: recompute from raw inputs, flag discrepancies

---

## Stage 4: DELIVER (Service Deployment)

### Rules
- Client config.json must have all required platform credentials before deploy
- SQLite databases must be created with correct schema on first run
- Zalo webhook must respond to test ping before going live
- Sync daemon must complete one full cycle without errors before enabling auto-mode
- Inventory thresholds must be explicitly set (no implicit defaults in production)

### Metrics
- **config_validity**: all required fields present and non-empty (target: 100%)
- **first_sync_success**: first sync cycle completes without errors (target: 100%)
- **webhook_reachable**: Zalo webhook responds to test (target: 100%)
- **schema_integrity**: all expected tables and columns exist (target: 100%)
- **error_rate_24h**: errors in first 24 hours / total operations (target: ≤2%)

### Threshold: 95
### Max Iterations: 3

### Improvement Actions
- If config_validity < 100%: prompt operator for missing credentials
- If first_sync_success < 100%: check API credentials, retry with verbose logging
- If webhook_reachable < 100%: verify URL, check firewall/DNS
- If error_rate_24h > 2%: analyze error logs, patch and re-deploy

---

## Stage 5: REPORT (Monthly Reporting)

### Rules
- Report must cover the full calendar month (day 1 to last day)
- All numerical data must come from orders.db (no hardcoded/estimated values)
- MoM comparison requires previous month data; if missing, note "N/A" not fake numbers
- HTML report must render correctly in Chrome, Safari, and mobile
- Email delivery must be confirmed (Gmail API message ID logged)

### Metrics
- **data_completeness**: % of days in month with order data (target: ≥90%)
- **calculation_accuracy**: MoM growth, totals, averages are mathematically correct (target: 100%)
- **render_quality**: HTML passes basic structure check (target: 100%)
- **delivery_success**: email sent and confirmed (target: 100%)
- **crm_updated**: "Next Report Due" field updated in CRM (target: 100%)

### Threshold: 90
### Max Iterations: 2

### Improvement Actions
- If data_completeness < 90%: check sync logs for gaps, backfill if possible
- If calculation_accuracy < 100%: recompute from raw SQL, diff against report
- If delivery_success < 100%: retry email send, check recipient address
- If crm_updated < 100%: retry Sheets API update

---

## Global Rules

### Agent Loop Protocol
1. **Generate**: Run the pipeline stage normally
2. **Evaluate**: Score output against stage metrics using the rules above
3. **Decide**: If composite score ≥ threshold → PASS, move to next stage
4. **Improve**: If score < threshold AND iterations < max → apply improvement actions, re-run
5. **Escalate**: If max iterations reached and still failing → log failure, alert operator

### Metric Calculation
- Each metric scores 0-100
- Composite score = weighted average of stage metrics (equal weight by default)
- Scores are logged to `data/metrics_history.json` for trend analysis

### Escalation
- Any stage that fails after max iterations triggers a Zalo alert to the operator
- The alert includes: stage name, composite score, failing metrics, iteration count
- Pipeline halts at the failing stage (does not proceed to next stage)
