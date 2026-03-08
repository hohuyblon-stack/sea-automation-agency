# Case Study: Xưởng Dịch Vụ Ô Tô — Tự Động Hóa Quản Lý Xe Ra Vào

## Khách hàng

Xưởng dịch vụ ô tô tại Hà Nội, xử lý 30-50 xe/ngày. Quản lý xe ra vào, theo dõi tồn kho trong xưởng, và báo cáo năng suất cho quản lý.

## Vấn đề

Trước khi triển khai hệ thống tự động:

- **Ghi chép bằng tay**: Nhân viên ghi biển số, thời gian vào/ra trên sổ giấy hoặc Excel — dễ sai, khó tra cứu
- **Không biết xe nào đang trong xưởng**: Quản lý phải hỏi trực tiếp hoặc đi kiểm tra
- **Báo cáo cuối ngày mất 30-45 phút**: Tổng hợp thủ công từ nhiều nguồn
- **Xe nằm quá lâu không ai biết**: Không có cảnh báo khi xe vượt thời gian dự kiến

## Giải pháp

Hệ thống chatbot Telegram tích hợp:

1. **Nhận diện biển số tự động (OCR)**: Nhân viên chỉ cần chụp ảnh biển số → hệ thống tự nhận diện và ghi nhận xe vào/ra
2. **Google Sheets làm cơ sở dữ liệu**: Toàn bộ dữ liệu xe, lịch sử ra vào, và log lưu trên Google Sheets — ai cũng xem được, không cần cài phần mềm
3. **Cảnh báo tự động qua Telegram**:
   - Xe trong xưởng > 24 giờ → cảnh báo vàng
   - Xe trong xưởng > 48 giờ → cảnh báo đỏ (khẩn)
4. **Báo cáo tự động**:
   - Gõ `TONKHO` → xem xe đang trong xưởng ngay lập tức
   - Gõ `BAOCAO` → báo cáo tổng hợp trong ngày
   - Gõ `NANGSUAT` → so sánh năng suất với hôm qua, phân tích theo khung giờ
   - Báo cáo hàng ngày gửi tự động cho quản lý

## Kết quả

| Chỉ số | Trước | Sau | Cải thiện |
|--------|-------|-----|-----------|
| Thời gian ghi nhận xe vào/ra | 2-3 phút/xe (ghi tay) | 5 giây (chụp ảnh) | ~95% nhanh hơn |
| Thời gian tổng hợp báo cáo | 30-45 phút/ngày | Tự động, 0 phút | Tiết kiệm ~3-4 tiếng/ngày |
| Xe nằm quá hạn không phát hiện | Thường xuyên | Cảnh báo tự động 24h/48h | Giảm đáng kể |
| Sai sót ghi chép | 5-10 lỗi/ngày | Gần như 0 (OCR + tự động) | ~95% |

## Thời gian triển khai

- Phát triển: 1 tuần
- Đào tạo nhân viên: 1 buổi (chỉ cần biết chụp ảnh và gõ lệnh trong Telegram)
- Hệ thống chạy ổn định từ ngày đầu tiên

## Công nghệ sử dụng

- Telegram Bot (giao diện nhân viên)
- Google Vision AI (nhận diện biển số)
- Google Sheets (lưu trữ dữ liệu)
- Node.js trên Render (server)

## Chi phí vận hành

- Hosting: ~0 đồng (Render free tier)
- Google Vision OCR: ~0 đồng (1,000 ảnh miễn phí/tháng)
- Google Sheets: miễn phí
- **Tổng chi phí vận hành hàng tháng: gần như 0 đồng**

---

*Liên hệ để trao đổi thêm về giải pháp tự động hóa phù hợp cho doanh nghiệp của bạn.*
