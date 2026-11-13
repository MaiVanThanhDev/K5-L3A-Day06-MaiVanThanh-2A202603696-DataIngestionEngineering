# Kế hoạch trước thử nghiệm

Trạng thái: đã định nghĩa cách so sánh; chưa có kết quả benchmark.

- Corpus: báo cáo thực tập cá nhân về hệ thống quản lý thư viện; manifest ghi các trang được dùng.
- Model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 qua FastEmbed ONNX local CPU, 384 chiều theo model; chương trình kiểm tra chiều thực và hash file model.
- Store: PostgreSQL + pgvector trong Docker; cosine exact search, top-3.
- A: fixed 900 ký tự, overlap 90, không filter.
- B: gộp theo đoạn, tối đa 900 ký tự, không overlap, không filter.
- C: chunk và embedding giống B; chỉ áp dụng metadata filter từ input câu hỏi.
- A–B thay thuật toán chia đoạn (bao gồm cách overlap); B–C chỉ thay filter.
- Giả thuyết: B giữ ý tốt hơn A; C giảm nhầm phạm vi khi câu hỏi có filter. Đây là giả thuyết, có thể bị bác bỏ.
- Chọn cấu hình trên dev: Hit@3 cao nhất → Hit@1 cao nhất → ít chunk hơn → tên cấu hình theo thứ tự chữ.
- Chốt 15 dev / 5 test trước khi chạy. Chạy ba cấu hình trên test sau khi lưu selection.json; test không dùng để chỉnh.
- Coherence: 10 source/page đầu theo thứ tự, vị trí giữa trang. Nếu rơi vào khoảng trắng, lấy chunk gần nhất; nếu overlap bao phủ nhiều chunk, chấm mọi chunk được chọn và báo n thực tế.
- Metadata và grounding: cùng các câu test, mọi top-3 trả về. Nhãn do học viên kiểm tra nguồn, ghi tên người chấm/lý do và nguy cơ thiên lệch.
- Chi phí API: 0 khi thực sự chạy local; không định giá điện/phần cứng. Thời gian đo tách embedding, upsert hai lần và retrieval.
