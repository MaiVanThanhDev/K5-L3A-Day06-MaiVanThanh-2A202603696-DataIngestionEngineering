# Benchmark đồ án cá nhân

Bộ câu hỏi trong questions.jsonl được xây từ nội dung báo cáo thật trước khi chạy retrieval. Mẫu trống ban đầu đã được dọn vì bộ câu hỏi chính thức đã có đủ 20 câu.

- Chia cố định q01–q15 dev, q16–q20 test trước thí nghiệm.
- Test ưu tiên công cụ kiểm thử/giới hạn và hướng phát triển; dev ưu tiên thiết kế/nghiệp vụ. Cùng một đồ án nên vẫn có rò rỉ chủ đề; test nhỏ không đại diện tổng quát.
- Ít nhất 3 câu có filter, trong đó ít nhất 1 test. Phạm vi chương được nói ngay trong câu hỏi, không lấy gold source/answer để tạo filter.
- Metadata category lấy từ chương thật: chuong_2 hoặc chuong_3. Filter theo chương là phạm vi khá rộng; không thay việc đọc đúng điều kiện/ngoại lệ.
- Evidence là trích đoạn đúng trang của snapshot chuẩn hóa; --validate-only kiểm tra sự hiện diện. Tác giả cần rà lại đáp án/điều kiện trước lần chạy đầu.
- alternative_gold tùy chọn: [{"source_id":"id","page":12,"evidence_quote":"..."}]. Nếu thấy nguồn tương đương hợp lệ, ghi rõ và xác nhận; không sửa gold chỉ để làm điểm đẹp.

Tiêu chí chọn cấu hình đã ghi trong starter/configs/strategies.json. Không dùng test để tinh chỉnh.
