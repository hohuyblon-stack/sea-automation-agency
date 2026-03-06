# BÁO GIÁ DỊCH VỤ HỆ THỐNG CẢNH BÁO TỒN KHO
# Inventory Alert System — Service Proposal

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

Với số lượng SKU ngày càng tăng, việc theo dõi tồn kho thủ công dẫn đến **oversell** (bán quá số lượng), hết hàng không biết, và mất doanh thu vì sản phẩm bán chạy hết stock mà không được nhập bổ sung kịp thời.

---

Based on our conversation, {{business_name}} manages inventory manually on **{{platform}}** (~{{monthly_orders}} orders/month). The main pain point:
> *{{pain_point}}*

As SKU count grows, manual inventory tracking leads to **overselling**, invisible stockouts, and lost revenue from best-sellers going out of stock without timely replenishment.

---

## 2. GIẢI PHÁP ĐỀ XUẤT / Proposed Solution

### Hệ thống Cảnh Báo Tồn Kho Thông Minh / Smart Inventory Alert System

Mình sẽ xây dựng một hệ thống tự động theo dõi tồn kho, gửi cảnh báo kịp thời qua Zalo khi hàng sắp hết, và tạo báo cáo tồn kho hàng ngày.

---

**Component 1: Real-Time Stock Monitoring**
- Connects to {{platform}} API and syncs stock levels every 15 minutes
- Tracks current quantity, daily sales velocity, and days-of-supply remaining
- Automatically detects fast-moving SKUs and adjusts alert thresholds

**Component 2: Multi-Level Zalo Alerts**
- ⚠️ **Warning alert** — when stock falls below 7-day supply
- 🔴 **Critical alert** — when stock falls below 3-day supply
- 🚫 **Stockout alert** — immediate notification when any SKU hits zero
- Alerts include: product name, current stock, daily sales rate, recommended reorder quantity

**Component 3: Daily Inventory Report**
- Sends a daily summary to your Zalo at 8am:
  - Top 10 fastest-selling products and their remaining stock
  - Products at risk of stockout within 7 days
  - Oversell incidents in the last 24 hours
  - Suggested reorder list with quantities

**Component 4: Oversell Prevention**
- Auto-pauses listings on {{platform}} when stock hits zero
- Re-activates listings automatically when stock is replenished
- Prevents negative inventory situations across all platforms

---

## 3. KẾT QUẢ KỲ VỌNG / Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Stockout incidents per month | 5–15 lần/times | Near zero |
| Oversell rate | 3–8% | 0% |
| Time spent checking inventory | 1–2 giờ/hours per day | 0 (automated) |
| Revenue lost to stockouts | ~5–10% monthly revenue | < 1% |
| Reorder response time | 2–3 ngày/days | Same day |

**Estimated revenue recovery: 5–10% increase from eliminated stockouts**

---

## 4. PHẠM VI CÔNG VIỆC / Scope of Work

**Bao gồm / Included:**
- [x] API integration with {{platform}} for inventory data
- [x] Real-time stock monitoring daemon (runs 24/7)
- [x] Zalo notification bot with 3-level alert system
- [x] Daily inventory report generation
- [x] Auto-pause/resume logic for zero-stock listings
- [x] 30 days of post-launch support
- [x] Full documentation and handover guide

**Không bao gồm / Not included:**
- [ ] Hardware/server costs (recommend using a VPS at ~200K VND/month)
- [ ] {{platform}} API registration fees (if applicable)
- [ ] Physical inventory counting or warehouse management

---

## 5. TIMELINE

| Ngày / Day | Milestone |
|-----------|-----------|
| Day 1     | API setup, credentials, environment config |
| Day 2–3   | Stock monitoring core + alert logic |
| Day 4     | Zalo bot + multi-level notification system |
| Day 5     | Daily reporting + oversell prevention + UAT testing |

**Tổng thời gian: 5 ngày làm việc / Total: 5 business days**

---

## 6. CHI PHÍ / Investment

| Hạng mục / Item | Giá / Price |
|----------------|-------------|
| Inventory Alert System (one-time setup) | **8,000,000 VND** (~$320 USD) |
| Monthly maintenance (optional) | 1,500,000 VND/tháng |

**Tổng thanh toán / Total due:** 8,000,000 VND

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
