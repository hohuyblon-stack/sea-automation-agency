# Case Study: Auto Service Workshop — Vehicle Tracking Automation

## Client

Auto service workshop in Hanoi, processing 30-50 vehicles/day. Manages vehicle check-in/check-out, workshop inventory tracking, and productivity reporting for management.

## Problem

Before automation:

- **Manual record-keeping**: Staff wrote license plates and timestamps on paper or Excel — error-prone, hard to search
- **No real-time workshop visibility**: Managers had to ask staff or walk the floor to know which vehicles were on-site
- **End-of-day reports took 30-45 minutes**: Manual compilation from multiple sources
- **Vehicles sitting too long went unnoticed**: No alerts when vehicles exceeded expected service time

## Solution

Telegram chatbot with integrated automation:

1. **Automatic license plate recognition (OCR)**: Staff snap a photo of the license plate — system auto-recognizes and logs the vehicle in/out
2. **Google Sheets as database**: All vehicle data, history, and logs stored on Google Sheets — accessible to anyone, no software to install
3. **Automated Telegram alerts**:
   - Vehicle in workshop > 24 hours — warning alert
   - Vehicle in workshop > 48 hours — urgent alert
4. **Instant reports**:
   - `TONKHO` — current vehicles in workshop
   - `BAOCAO` — daily summary report
   - `NANGSUAT` — productivity comparison vs. yesterday, broken down by time slot
   - Daily report auto-sent to managers

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Vehicle check-in/out time | 2-3 min/vehicle (manual) | 5 seconds (photo) | ~95% faster |
| Report compilation time | 30-45 min/day | Automatic, 0 min | Saves ~3-4 hours/day |
| Overdue vehicles undetected | Frequent | Auto-alert at 24h/48h | Significant reduction |
| Record-keeping errors | 5-10 errors/day | Near zero (OCR + automation) | ~95% |

## Timeline

- Development: 1 week
- Staff training: 1 session (just take photos and type commands in Telegram)
- System stable from day one

## Tech Stack

- Telegram Bot (staff interface)
- Google Vision AI (license plate recognition)
- Google Sheets (data storage)
- Node.js on Render (server)

## Operating Cost

- Hosting: ~$0 (Render free tier)
- Google Vision OCR: ~$0 (1,000 images free/month)
- Google Sheets: free
- **Total monthly operating cost: near zero**

---

*Contact us to discuss automation solutions tailored for your business.*
