# BÁO GIÁ DỊCH VỤ TỰ ĐỘNG HÓA ĐƠN HÀNG ĐA SÀN
# Multi-Platform Order Sync Automation — Service Proposal

---

**Khách hàng / Client:** {{client_name}}
**Doanh nghiệp / Business:** {{business_name}}
**Ngày / Date:** {{proposal_date}}
**Mã báo giá / Proposal ID:** {{proposal_id}}

---

## 1. HIỂU VẤN ĐỀ CỦA BẠN / Understanding Your Challenge

{{business_name}} hiện đang bán hàng trên **{{platform}}** với khoảng **{{monthly_orders}} đơn/tháng**.

Dựa trên cuộc trò chuyện của chúng ta, vấn đề chính là:
> *{{pain_point}}*

Theo khảo sát các shop có quy mô tương tự, xử lý thủ công {{monthly_orders}} đơn/tháng mất khoảng **{{manual_hours_per_day}} giờ mỗi ngày** — tức gần **{{manual_hours_per_month}} giờ mỗi tháng** chỉ cho việc nhập liệu và xác nhận đơn.

---

Based on our conversation, {{business_name}} currently processes orders manually on **{{platform}}** (~{{monthly_orders}} orders/month). The main pain point:
> *{{pain_point}}*

Manual processing at this volume costs approximately **{{manual_hours_per_day}} hours/day** (~{{manual_hours_per_month}} hours/month) on data entry, order confirmation, and inventory updates alone.

---

## 2. GIẢI PHÁP ĐỀ XUẤT / Proposed Solution

### Hệ thống Đồng Bộ Đơn Hàng Tự Động / Automated Order Sync System

Mình sẽ xây dựng một hệ thống tự động kết nối với API của {{platform}}, xử lý đơn hàng theo thời gian thực và gửi báo cáo về Zalo/email mỗi ngày.

---

**Component 1: Order Auto-Sync**
- Pulls all new orders from {{platform}} every 15 minutes
- Auto-confirms orders, updates status, generates shipping labels
- Deduplicates and normalizes data across platforms

**Component 2: Inventory Auto-Update**
- Syncs stock levels back to {{platform}} after each sale
- Sends low-stock alerts to Zalo when items fall below threshold
- Prevents overselling with real-time lock mechanism

**Component 3: Daily Reporting**
- Sends a daily summary to your Zalo at 9am:
  - Orders received (new, processing, shipped, cancelled)
  - Revenue vs. yesterday
  - Top-selling products
  - Low stock warnings

**Component 4: Error Monitoring**
- Auto-alerts on API failures, rejected orders, payment issues
- Weekly system health report

---

## 3. KẾT QUẢ KỲ VỌNG / Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Daily order processing time | {{manual_hours_per_day}} giờ/hours | ~20 phút/min |
| Order entry errors | ~5–10% | 0% |
| Stock sync delay | Manual (hours) | Real-time |
| Reporting | Manual (monthly) | Daily automated |
| Oversell incidents | Occasional | Eliminated |

**Time saved: ~{{manual_hours_per_month}} hours/month**
**At 100,000 VND/hour labor cost: {{labor_cost_saved_vnd}} VND/month saved**

---

## 4. PHẠM VI CÔNG VIỆC / Scope of Work

**Bao gồm / Included:**
- [x] API integration with {{platform}} (Official Partner API)
- [x] Order sync daemon (runs 24/7 on cloud or your server)
- [x] Zalo notification bot setup
- [x] Daily/weekly report dashboard
- [x] Low-stock alert system
- [x] 30 days of post-launch support
- [x] Full documentation and handover guide

**Không bao gồm / Not included:**
- [ ] Hardware/server costs (recommend using a VPS at ~200K VND/month)
- [ ] {{platform}} API registration fees (if applicable)
- [ ] Changes to order management workflow beyond agreed scope

---

## 5. TIMELINE

| Ngày / Day | Milestone |
|-----------|-----------|
| Day 1–2   | API setup, credentials, environment config |
| Day 3–4   | Order sync core development & testing |
| Day 5     | Zalo bot + notification system |
| Day 6     | Reporting dashboard + alerts |
| Day 7     | UAT testing with live data, handover |

**Tổng thời gian: 7 ngày làm việc / Total: 7 business days**

---

## 6. CHI PHÍ / Investment

| Hạng mục / Item | Giá / Price |
|----------------|-------------|
| Order Sync System (one-time setup) | **15,000,000 VND** (~$600 USD) |
| Monthly maintenance (optional) | 2,000,000 VND/tháng |

**Tổng thanh toán / Total due:** 15,000,000 VND

**Phương thức thanh toán / Payment terms:**
- 50% khi ký hợp đồng / 50% upfront on signing
- 50% khi nghiệm thu / 50% on delivery & acceptance

**Cam kết hoàn tiền / Guarantee:**
Nếu hệ thống không hoạt động đúng theo mô tả trong 30 ngày đầu, hoàn tiền 100%.
*If the system doesn't perform as described within the first 30 days, full refund.*

---

## 7. THÔNG TIN LIÊN HỆ / Contact

**{{sender_name}}**
Email: {{sender_email}}
Zalo: {{sender_zalo}}

---

*Báo giá này có hiệu lực trong 14 ngày kể từ ngày {{proposal_date}}.*
*This proposal is valid for 14 days from {{proposal_date}}.*

---

**Để xác nhận, vui lòng reply email này hoặc nhắn Zalo.**
**To confirm, reply to this email or message on Zalo.**
