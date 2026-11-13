# Kiểm tra corpus trước thí nghiệm

- PDF học viên cung cấp: 2221050673_MaiVanThanh_BaoCaoTTDN.pdf; bản làm việc local: data/private/bao_cao.pdf.
- Đã đọc bằng pypdf: 54 trang vật lý; không cần OCR cho những trang được chọn.
- Chọn 16–23 và 28–51: **32 trang**, tổng **44.082 ký tự** sau chuẩn hóa/bỏ header/footer.
- Loại 1–2 (bìa), 3–4 (đề cương/thông tin thực tập và liên hệ), 5–9 (mục lục/danh mục), 10–11 (phần mở đầu không dùng), 12–15 (giới thiệu đơn vị/lịch thực tập), 24–27 (chủ yếu sơ đồ hình ảnh, không OCR), 52 (đoạn kết rất ngắn), 53–54 (tham khảo).
- Các trang 34–36 vẫn được tính: có ảnh giao diện nhưng có đoạn giải thích nghiệp vụ hữu ích trích xuất được; không tính ảnh thành một trang bổ sung.
- category được gán theo chương thật: chuong_2 cho 16–50; chuong_3 cho 51. Phạm vi rộng, phân bố lệch; đây là hạn chế của filter.
- Header/footer lặp đã bỏ theo mẫu trong preparation.json; page luôn là trang PDF vật lý gốc, không đánh lại từ 1.
- Giữ nguyên lỗi khoảng cách trong từ của bản PDF (ví dụ chữ bị tách bởi khoảng trắng), không tự sửa nội dung. Bảng chuyển thành text nên có thể mất bố cục; cần nêu trong báo cáo.
- Hash PDF và snapshot trong manifest.json giúp kiểm tra đúng phiên bản.
- Quyền chia sẻ: ngày 13/11/2026, Mai Văn Thanh xác nhận tài liệu được phép chia sẻ phục vụ bài nộp LAB6. Trạng thái quyền trong manifest/preparation được cập nhật theo xác nhận này; nội dung corpus và kết quả thí nghiệm giữ nguyên.

Tái tạo từ bản PDF local bằng scripts/rebuild_corpus.py; không cần tải tài liệu từ Internet.
