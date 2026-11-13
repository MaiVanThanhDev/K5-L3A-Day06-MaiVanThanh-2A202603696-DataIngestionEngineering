# Pipeline LAB6 — PostgreSQL + pgvector

Mã nguồn đã được hiện thực thay cho các hàm TODO của starter. Xem [cách chạy trong báo cáo cá nhân](../report/individual/2A202603696_MaiVanThanh.md#cách-chạy-và-tái-lập) để chạy bằng Docker Desktop với Python 3.12, embedding đa ngữ local và PostgreSQL.

- src/ingestion.py: đọc PDF/JSONL, chuẩn hóa, kiểm tra manifest/hash, log trang lỗi/rỗng.
- src/chunking.py: fixed-size/overlap và chia theo đoạn có giới hạn, ID ổn định và offset nguồn.
- src/embeddings.py: FastEmbed ONNX CPU, query_embed/passage_embed, kiểm tra vector và hash model.
- src/store.py: schema pgvector, upsert không nhân đôi, xóa chunk cũ trong cùng transaction, filter JSONB và exact cosine top-k.
- src/evaluation.py: kiểm tra source/page + evidence, gold thay thế, tổng hợp dev/test.
- src/run.py: validate corpus/benchmark, chạy A/B/C, khóa lựa chọn trên dev, lưu trace và mẫu chấm thủ công.
- scripts/prepare_pdf.py: kiểm tra PDF và tạo manifest từ trang/phạm vi chương được xác minh.
- scripts/summarize_audit.py: tổng hợp nhãn đã chấm, từ chối nhãn còn trống hoặc bản ghi bị thay nguồn.
- tests/: kiểm tra logic bằng fixture tổng hợp; không thay kết quả benchmark thật.

Lệnh thực hiện từ starter/: python -m src.run --help. Nếu dùng Python local phải có dependencies, DATABASE_URL trong .env và model tải được. Khi gặp lỗi, pipeline dừng và ghi stage/error type, không ghi credential hoặc fallback sang mock.

Compose chỉ mở PostgreSQL ở 127.0.0.1:55433 với mật khẩu dành riêng cho lab local. Không xóa volume khi chưa xác nhận dữ liệu cần giữ.
