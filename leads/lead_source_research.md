# Vietnam E-Commerce Lead Sources — Research Report

> Alternatives to Google Maps scraping for finding Vietnam e-commerce sellers with actionable contact info.

---

## Summary Recommendation

| Priority | Source | Data Quality | Email Availability | Cost | Next Step |
|----------|--------|-------------|-------------------|------|-----------|
| 🔴 **#1** | **Shopee Seller Scraper** (Apify) | ★★★★★ | Shop name, ratings, products — no email | ~$49/mo | Build scraper → enrich via Hunter.io |
| 🔴 **#2** | **Facebook Seller Groups** | ★★★★☆ | Posts often include Zalo/phone/email | Free | Expand existing `facebook_group_leads.py` |
| 🟡 **#3** | **Hunter.io domain search** | ★★★☆☆ | Verified emails from domains | Free tier: 25/mo | Use for sellers with own websites |
| 🟡 **#4** | **Vietnam business directories** | ★★★☆☆ | Phone, sometimes email | Free | Script scraper for SooPage/ZipLeaf |
| 🟢 **#5** | **Apollo.io** | ★★☆☆☆ | Large DB but VN data ~60% accurate | Free tier available | Supplement only |

---

## Tier 1: Platform Seller Scrapers (Best ROI)

### Shopee Seller Scraper via Apify
- **What it gives you:** Shop name, rating, followers, response rate, products, location
- **What it doesn't give:** Direct email or phone (Shopee hides PII)
- **How to use:** Scrape top sellers by category → extract shop names + website URLs → enrich emails via Hunter.io or manual Zalo outreach
- **Tools:** [Apify Shopee Seller Scraper](https://apify.com), [Scrapeless](https://scrapeless.com), [Bright Data](https://brightdata.com)
- **Anti-scraping:** Shopee has aggressive bot detection. Apify handles proxy rotation and CAPTCHA solving
- **Cost:** Apify ~$49/mo for sufficient volume; Scrapeless similar

### TikTok Shop / Lazada Seller Pages
- Same approach — scrape seller listings from category pages
- Less tooling available vs Shopee; may need custom Playwright scraper
- Consider building `leads/scrapers/shopee_seller_leads.py` as next scraper

---

## Tier 2: Community-Based (Highest Intent Leads)

### Facebook Groups (Expand Current Scraper)
- **Key groups to target:**
  - "Lập Nghiệp với Shopee" (official Shopee seller community)
  - "Cộng đồng người bán hàng Shopee Việt Nam"
  - TikTok Shop seller groups (search: "Cộng đồng TikTok Shop")
  - General e-commerce: "Hội bán hàng online Việt Nam"
- **Why this works:** Sellers in these groups actively post asking for help with order management, inventory problems — exactly the pain points we solve
- **Data available:** Posts often contain Zalo numbers, phone, sometimes email
- **Next step:** Enhance `facebook_group_leads.py` to scrape more groups and extract Zalo/phone from post text via regex

### Zalo Groups & Official Accounts
- Shopee VN runs the official Zalo channel "Shopee Việt Nam Kênh Thông Tin Người Bán"
- Many local seller communities have Zalo groups (harder to scrape but high-quality leads)
- Best used for manual prospecting rather than automation

---

## Tier 3: Email Enrichment Tools

### Hunter.io
- **Best for:** Finding verified emails from known business domains
- **Workflow:** Get seller's website URL from Shopee profile → Hunter.io domain search → verified email
- **VN coverage:** Moderate — works well for businesses with .vn or .com domains
- **Free tier:** 25 searches/month; paid from $49/mo
- **API available:** Yes, easy to integrate into pipeline

### Apollo.io
- **Database:** 275M+ contacts globally
- **VN accuracy:** ~60% for contact details outside US/EU — use as supplement, not primary
- **Best for:** Finding decision-makers at larger e-commerce companies (>10 employees)
- **Free tier:** 10K credits/mo (generous)
- **Caveat:** Small Shopee sellers are unlikely to be in Apollo's database

---

## Tier 4: Vietnam Business Directories

| Directory | Records | Email Available | Scraping Difficulty |
|-----------|---------|-----------------|---------------------|
| **SooPage** (soopage.com) | 245K+ companies | Sometimes | Easy (structured HTML) |
| **ZipLeaf** (zipleaf.com/vn) | Large | Sometimes | Easy |
| **Yellow Pages VN** | Medium | Phone mostly | Moderate |
| **Cổng Thông Tin DN** (national registry) | All registered businesses | Registration data only | Hard (CAPTCHA) |

- These are general business directories — filter for e-commerce/retail categories
- Best for supplementing platform-scraped leads with contact details

---

## Recommended Pipeline (Next Scrapers to Build)

```
1. Shopee Category Scraper (Apify API)
   └─ Shop name, URL, location, rating, products
        │
2. Website Extractor
   └─ Check if shop has own website/fanpage
        │
3. Hunter.io Enrichment (or manual Zalo lookup)
   └─ Verified email from domain
        │
4. Facebook Group Posts (existing scraper, expanded)
   └─ Zalo/phone/email from seller posts
        │
5. Merge + Deduplicate + Score (existing qualify_leads.py)
   └─ qualified_leads.csv → send_sequence.py
```

### New Scrapers to Prioritize

1. **`leads/scrapers/shopee_category_leads.py`** — Use Apify API to pull top sellers from Shopee categories (thoi trang, my pham, dien tu). Output: shop name, URL, city, product count, rating
2. **`leads/scrapers/hunter_enrichment.py`** — Take website URLs, batch-query Hunter.io API, append verified emails to CSV
3. **Expand `facebook_group_leads.py`** — Add more group URLs, improve Zalo/phone extraction regex
