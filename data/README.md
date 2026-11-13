# Corpus đồ án cá nhân

Nguồn: báo cáo thực tập về hệ thống quản lý thư viện bằng Java Spring Boot do học viên cung cấp. File gốc được giữ trong data/private/ và không tự đưa vào Git.

- Manifest ghi trang vật lý, hash PDF/snapshot, số ký tự, nguồn metadata và phép biến đổi.
- Loại bìa, thông tin thực tập/liên hệ, mục lục, danh mục hình/bảng, trang chủ yếu là sơ đồ không trích xuất được, trang kết thúc ngắn và tài liệu tham khảo.
- Chỉ dùng nội dung chương 2 và phần nội dung chương 3. category = chuong_2 hoặc chuong_3, lấy từ chương thực tế; section mô tả chương.
- PDF có trang vật lý nên không bắt buộc mỗi trang 1500 ký tự. Ngưỡng 1500 áp dụng đơn vị text tự chia khi không có phân trang.
- Header/footer lặp chứa tên/lớp được bỏ nếu khớp mẫu đã ghi; giữ số trang vật lý trong metadata.
- PDF có lỗi khoảng cách do xuất văn bản; không tự ghép lại chữ khi chưa xác minh. Đây là hạn chế cần ghi trong báo cáo.

Mai Văn Thanh đã xác nhận ngày 13/11/2026 rằng tài liệu được phép chia sẻ phục vụ bài nộp LAB6. Xác nhận được ghi trong manifest.json và corpus_review.md; không tự gán thêm giấy phép mở. Snapshot và trace chứa nội dung của chính tài liệu này. File PDF gốc vẫn được giữ trong data/private/ và gitignore.
