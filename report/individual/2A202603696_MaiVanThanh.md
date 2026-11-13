# Báo cáo cá nhân — Day 6

Họ tên: Mai Văn Thanh · Mã học viên: 2A202603696 · Lớp: L3A

## Dữ liệu và pipeline

Corpus là báo cáo cá nhân về hệ thống RESTful API quản lý thư viện bằng Java Spring Boot. PDF có 54 trang vật lý; chọn 32 trang nội dung (16–23, 28–51), tổng 44.082 ký tự chuẩn hóa. [Manifest](../../data/manifest.json) ghi hash, trang, số ký tự và quyền; [kiểm tra corpus](../../data/corpus_review.md) giải thích các trang bị loại. Mai Văn Thanh cung cấp tài liệu và xác nhận ngày 13/11/2026 rằng tài liệu được phép chia sẻ phục vụ bài nộp LAB6.

Dùng pypdf layout mode, chuẩn hóa Unicode NFC/khoảng trắng, giữ ngắt đoạn và bỏ header/footer lặp theo mẫu lưu trong preparation.json. Không OCR hoặc tự ghép lại những chữ bị tách khoảng trắng. Trang sơ đồ 24–27 không dùng; bảng có thể mất cấu trúc khi chuyển thành text. Mọi trang được chọn đều đọc được chữ.

Metadata có document_id, source, page (trang PDF vật lý), category, section, language và offset ký tự. category = chuong_2/chuong_3, lấy từ chương thật. source/page dùng truy vết; category giới hạn phạm vi chương do người hỏi cung cấp. Filter khá rộng và phân bố chương lệch là hạn chế.

Model thật: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, FastEmbed ONNX CPU, **384 chiều thực tế**; query/document dùng query_embed/passage_embed. Snapshot upstream: faf4aa4225822f3bc6376869cb1164e8e3feedd0. File trọng số đã đối chiếu SHA256 nguồn chính thức; toàn bộ file model được fingerprint trong run_dev.json/run_test.json. Nội dung đồ án không gửi đến API.

Môi trường chạy: Python 3.12.16; PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1); pgvector 0.8.7; FastEmbed 0.8.1; ONNX Runtime 1.31.1; NumPy 2.5.4; psycopg 3.3.9; pypdf 6.21.4. Store dùng cosine exact search, lưu trong volume PostgreSQL. Python 3.14 alpha trên host không import được NumPy/psycopg; đã chạy thành công bằng Python stable trong container.

## Cấu hình và benchmark

| Cấu hình | Chia chunk                                 | Filter                    | Chunk trong database |
| -------- | ------------------------------------------ | ------------------------- | -------------------: |
| A        | Fixed 900 ký tự, overlap 90                | Không                     |                   66 |
| B        | Theo đoạn, tối đa 900 ký tự, không overlap | Không                     |                   69 |
| C        | Chunk và vector giống B                    | Chỉ khi câu hỏi có filter |                   69 |

A–B thay thuật toán chia đoạn (gồm overlap); B–C chỉ thay lọc. Cùng corpus, model, metric và benchmark. C dùng lại vector document của B trong cùng lượt chạy; không dùng vector ngẫu nhiên.

[Benchmark](../../benchmark/questions.jsonl): 20 câu được tạo trước retrieval, q01–q15 dev, q16–q20 test. q01/q12/q16/q20 có filter; 2 câu thuộc test. Evidence đã kiểm tra tồn tại ở nguồn/trang sau chuẩn hóa; 90 nhãn đánh giá đã được tác giả rà soát và chốt. Test ưu tiên công cụ kiểm thử, giới hạn và hướng phát triển; có giao thoa chủ đề vì cùng một đồ án.

Tiêu chí định trước: Hit@3 dev cao nhất → Hit@1 → ít chunk → tên cấu hình. Dev chọn **C**, được lưu trong [selection.json](../../results/selection.json) trước test. Corpus/benchmark/config/model giữ nguyên giữa hai lượt; không tinh chỉnh theo test.

## Kết quả retrieval

Một hit cần đúng nguồn/trang gold hoặc gold thay thế đã ghi **và chứa đủ evidence đã đăng ký trong một chunk**. Khớp chuỗi được chuẩn hóa khoảng trắng. Đây là điểm retrieval tự động theo bộ gold hiện tại, không phải độ chính xác câu trả lời LLM.

| Strategy | Split | Hit@1 (n/N)  | Evidence Hit@3 (n/N) | API USD |
| -------- | ----- | ------------ | -------------------- | ------: |
| A        | dev   | 6/15 (40.0%) | 8/15 (53.3%)         |       0 |
| A        | test  | 2/5 (40.0%)  | 2/5 (40.0%)          |       0 |
| B        | dev   | 7/15 (46.7%) | 9/15 (60.0%)         |       0 |
| B        | test  | 3/5 (60.0%)  | 5/5 (100.0%)         |       0 |
| C        | dev   | 7/15 (46.7%) | 10/15 (66.7%)        |       0 |
| C        | test  | 3/5 (60.0%)  | 5/5 (100.0%)         |       0 |

Tổng thời gian pipeline: dev **28.890 giây**, test **33.633 giây**; không tính tải image/model và cài môi trường. Chi phí API thực tế: **0 USD**, chưa định giá điện/phần cứng local.

| Strategy | Split | Chunk | Ký tự chunk | Embedding (s) | Upsert 2 lần (s) | Retrieval (s) |
| -------- | ----- | ----: | ----------: | ------------: | ---------------: | ------------: |
| A        | dev   |    66 |       47130 |         8.566 |            0.639 |         0.360 |
| A        | test  |    66 |       47130 |         7.611 |            0.224 |         0.192 |
| B        | dev   |    69 |       44008 |         8.066 |            0.242 |         0.515 |
| B        | test  |    69 |       44008 |         7.747 |            0.202 |         0.115 |
| C        | dev   |    69 |       44008 |       reuse B |            0.313 |         0.335 |
| C        | test  |    69 |       44008 |       reuse B |            0.375 |         0.201 |

Số ký tự A cao hơn vì overlap. Thời gian upsert bao gồm hai lần nạp để kiểm tra không nhân đôi, không phải latency ingest production. C tái sử dụng embedding B; thời gian embedding C gần 0 phản ánh cache, không chứng minh một model khác nhanh hơn. Thời gian đo một lượt trên cùng máy có nhiễu, không dùng để xếp hạng hiệu năng tổng quát.

Trace: [dev](../../results/traces_dev.jsonl), [test](../../results/traces_test.jsonl); [bảng CSV](../../results/retrieval_metrics.csv). Thống kê/phiên bản/hash: resources_dev.json, resources_test.json, run_dev.json, run_test.json trong results/.

## Coherence, metadata và grounding

**Người chấm thủ công: Mai Văn Thanh.** Tác giả đã rà soát và chốt đủ **90 nhãn** theo thang trong GUIDE.md; Codex hỗ trợ đề xuất/hiệu chỉnh nhãn ban đầu và đối chiếu bằng chứng. Bản 30 nhãn ban đầu được giữ nguyên tại [coherence.author_before_ai.jsonl](../../results/audit/coherence.author_before_ai.jsonl); trong lượt rà có AI hỗ trợ, 11 điểm coherence được đổi từ 2 xuống 1, các mẫu còn lại giữ điểm nhưng bổ sung lý do. Phương pháp, thay đổi từng mẫu, kiểm tra nguồn và xác nhận chốt nhãn của tác giả được lưu tại [review_method.json](../../results/audit/review_method.json).

Mẫu coherence gồm 10 vị trí nguồn và các chunk tương ứng; C có nội dung mẫu giống B nên dùng cùng cách chấm. Không hạ điểm chỉ vì caption bị cụt nếu yêu cầu nghiệp vụ vẫn đủ: ví dụ A/trang 22 giữ điểm 2. B/C/trang 21 chỉ đạt 1 vì câu nối từ trang trước và danh sách phạm vi thiếu phần còn lại. Metadata được đối chiếu lại với PDF gốc: hash khớp, 32 trang chuẩn hóa trích xuất lại khớp snapshot, và 45 đoạn khớp đúng trang/offset. Grounding được chấm theo câu hỏi, điều kiện và toàn bộ top-3, không lấy điểm Hit@3 làm nhãn thay thế.

| Strategy | Coherence /2 (n=10) | Metadata đúng/đủ (n=15) | Filter tuân thủ theo nhãn trên test | Grounding /2 (n=5) |
|---|---|---|---|---|
| A | 1.10 | 15/15 | 1/2 câu | 1.20 |
| B | 1.90 | 15/15 | 1/2 câu | 2.00 |
| C | 1.90 | 15/15 | 2/2 câu | 2.00 |

Filter tự động chỉ so sánh metadata của mọi top-3 với phạm vi **người hỏi yêu cầu**, kể cả A/B không áp dụng lọc; không thay việc kiểm tra metadata có đúng với nguồn. Chi tiết: [filter_compliance_auto.json](../../results/filter_compliance_auto.json).

Mẫu coherence: cùng 10 source/page đầu theo thứ tự, điểm giữa trang; mỗi chiến lược có 10 chunk. Metadata: 5 câu test × top-3 = 15 bản ghi mỗi chiến lược. Grounding: cùng 5 câu test cho mỗi chiến lược. Tổng cộng **30 dòng coherence, 45 dòng metadata, 15 dòng grounding**, đã lưu nhãn/lý do/người chấm trong results/audit/*.jsonl. Bảng trên dùng nhãn đánh giá; kiểm tra filter tự động là phép kiểm tra riêng. Phương pháp và nguồn gốc người chấm được khai báo trong phần này.

<!-- audit-distribution -->
Số câu grounding ở từng mức (0 / 1 / 2): A: 2 / 0 / 3; B: 0 / 0 / 5; C: 0 / 0 / 5.
<!-- /audit-distribution -->

## Phân tích và kết luận

**A–B:** B tăng Evidence Hit@3 từ 8/15 lên 9/15 trên dev, từ 2/5 lên 5/5 trên test. B có 69 chunk so với 66 của A nhưng ít ký tự được embed hơn do không overlap. Trên 10 vị trí đã chấm và chốt, coherence A là 1,10/2 và B là 1,90/2: A thường cắt mất đầu/cuối câu hoặc điều kiện; B vẫn có lỗi nối trang ở trang 21. Grounding test theo nhãn đã chốt là A 1,20/2 và B 2,00/2. Đây là nhận định trên mẫu nhỏ, có nguy cơ thiên lệch do tác giả tự đánh giá và dùng AI hỗ trợ cùng pipeline.

**B–C:** C tăng Hit@3 dev từ 9/15 lên 10/15, còn test cùng 5/5. Ở q01/dev, B trả một chunk Chương 3 ở hạng 1, làm trang gold 28 nằm ngoài top-3; C lọc Chương 2 nên trang 28 vào hạng 3. Ở q20/test, cả B và C đã hit hạng 1, nhưng B còn một kết quả Chương 2 không đúng phạm vi; C chỉ trả Chương 3. Filter cải thiện phạm vi kết quả mà không nhất thiết tăng Hit trên mọi câu.

Metadata đủ/đúng đều 15/15 cho mỗi chiến lược: cả kết quả ngoài phạm vi vẫn được gắn đúng chương/trang, nên không đánh đồng metadata sai với không áp dụng filter. Ba bản ghi vi phạm phạm vi q20 là A/trang 31, A/trang 22 và B/trang 20; vì chấm tuân thủ theo toàn bộ top-3 của từng câu, A/B đạt 1/2 câu và C đạt 2/2 câu có filter.

**Trường hợp grounding khác phép khớp gold:** A/q19 không đạt Evidence Hit@3 theo chuỗi gold đầy đủ, nhưng hạng 3 trang 51 vẫn giữ nguyên ba lý do cốt lõi: dùng H2, MySQL thực tế chưa xác nhận, chưa có bằng chứng VPS. Phần bị cắt thuộc đoạn nói về kiến trúc, không làm mất các lý do trả lời câu hỏi. Do đó chấm grounding 2, không sửa điểm retrieval và không suy diễn rằng top-3 đã chứa lỗi Connection refused. Ngược lại A/q16 và A/q20 không có đoạn đủ hỗ trợ phần nội dung được hỏi nên grounding 0.

**Hai ví dụ lỗi theo trace:**

1. **q12, A/dev, nguồn do-an-ca-nhan trang 36:** hạng 2 đúng trang nhưng bắt đầu giữa câu “xác nhận…”, không giữ trọn đoạn về tham số demo và điều kiện chưa phải quy định chính thức. A không hit; B/C có trọn evidence ở hạng 1. Đây là lỗi chia đoạn/mất điều kiện.
2. **q16, A/test, nguồn do-an-ca-nhan trang 40:** top-3 gồm hai chunk trang 49 và một chunk đầu trang 40, chưa tới đoạn Mockito/Repository và các tình huống mô phỏng. B/C có evidence ở hạng 2. Trả đúng một trang liên quan chưa đủ để tính hit.

Đối chiếu đầy đủ chunk ID và nội dung tại [failure_examples.json](../../results/failure_examples.json).

Chọn **C theo dev**, vì Hit@3 dev cao nhất và có filter theo input rõ ràng. Test B/C cùng 5/5 chỉ minh họa trên 5 câu, không chứng minh C tốt nhất cho mọi corpus hoặc mọi kiểu câu hỏi.

**Giới hạn và việc cần rà:** gold được tạo với AI hỗ trợ; có thể còn bằng chứng tương đương chưa được liệt kê. Ví dụ q01, A hạng 1 trang 20 chứa nội dung liên quan nhưng không thuộc gold trang 28; cần tác giả xác nhận độ đủ/tương đương, không tự tăng điểm. Các trường hợp cần rà nằm trong evidence_review_candidates.json. Giữ nguyên số đo đã đóng băng; nếu sửa gold sau khi xem kết quả, ghi rõ đây là đánh giá bổ sung hậu kiểm, không mô tả như holdout mới độc lập. Ngoài ra còn test nhỏ, một tài liệu, metadata chương lệch, lỗi khoảng trắng PDF và bảng mất bố cục.

Nếu làm tiếp: cải thiện trích xuất tài liệu/chunk theo heading và xây holdout mới. Không chỉnh cấu hình bằng test hiện tại rồi báo lại như kiểm tra độc lập.

## Kiểm chứng và AI hỗ trợ

16 unit test đã qua trong Docker. Kiểm tra live store bằng **vector thật** đã qua 6 mục: đếm ban đầu, nạp lại không trùng, metadata filter, giá trị filter được tham số hóa, xóa chunk cũ và cosine tự khớp. Sau restart PostgreSQL, A/B/C vẫn lần lượt **66/69/69**. Xem [store_verification.json](../../results/store_verification.json) và [docker_verification.json](../../artifacts/docker_verification.json).

Hậu kiểm tính lại metric từ trace và tái tạo 204 chunk, kiểm tra nguồn/metadata/evidence, bản chốt dữ liệu và lựa chọn từ dev; 16 phép kiểm tra đều đạt, không chạy lại test retrieval. Xem [postcheck.json](../../artifacts/postcheck.json). Giao diện cục bộ (`python ui/server.py`) hỗ trợ xem kết quả và chấm nhãn. Sau khi thêm giao diện, 23 kiểm thử Python đã qua trên host và Docker (16 pipeline + 7 lưu nhãn/HTTP). Kiểm tra Chrome trên máy tính và điện thoại qua 15 kiểm tra, gồm lưu đủ ba loại nhãn và tải lại vẫn giữ nhãn; không có lỗi JavaScript. Nhãn giả lập chỉ dùng trong thư mục tạm/bản sao để thử phần mềm, không đưa vào kết quả bài nộp.

**Mai Văn Thanh chấm thủ công và đã rà soát, chốt đủ 90 nhãn.** Codex hỗ trợ code, kiểm tra, trích xuất, soạn benchmark, chạy thí nghiệm, phân tích trace, đề xuất/hiệu chỉnh nhãn ban đầu và đối chiếu bằng chứng. Tác giả tự đánh giá bài làm và có sử dụng AI hỗ trợ nên vẫn có nguy cơ thiên lệch; chưa có đánh giá mù hoặc người chấm độc lập. Người học chịu trách nhiệm hiểu và giải thích được bài làm.

## Cách chạy và tái lập

Các lệnh thực hiện từ thư mục gốc của repo.

### Giao diện cục bộ

Nhấp đúp `MO_GIAO_DIEN.cmd`, hoặc chạy từ thư mục repo:

```powershell
python ui/server.py
```

Mở **http://127.0.0.1:8765**. Giao diện có bảng kết quả A/B/C, tìm kiếm chunk, đối chiếu top-3/evidence và chấm coherence/metadata/grounding. Không cần Docker hay cài thư viện để xem và chấm dữ liệu đã lưu. Giữ cửa sổ lệnh mở; `Ctrl+C` để dừng.

Ở **Đánh giá thủ công**, chọn tiêu chí, chiến lược và bản ghi; đọc nguồn, chọn nhãn, ghi người chấm/lý do rồi bấm **Lưu nhãn**. Nhãn được lưu trực tiếp vào `results/audit/*.jsonl`. Khi đủ **90/90**, bấm **Đồng bộ báo cáo** để cập nhật bảng điểm trong báo cáo và bảng kết quả. README gốc được giữ nguyên. Giao diện không tự chạy lại pipeline hoặc đổi gold.

Hậu kiểm dữ liệu đã lưu: `python starter/scripts/postcheck.py`. Xem [biên bản hậu kiểm](../../artifacts/postcheck.json). Nhãn đã lưu **90/90** và được tổng hợp vào báo cáo cá nhân.

Bản gốc ở `data/private/` được gitignore. Dữ liệu dẫn xuất và trace chứa nội dung báo cáo; quyền chia sẻ phục vụ bài nộp LAB6 đã được Mai Văn Thanh xác nhận ngày 13/11/2026 và ghi trong manifest.

### Chạy pipeline bằng Docker

Các lệnh chạy từ thư mục repo. Mở Docker Desktop ở chế độ Linux containers; container dùng Python 3.12 và PostgreSQL/pgvector. Nếu terminal chưa nhận Docker, mở terminal mới hoặc thêm đường dẫn cho phiên hiện tại:

```powershell
$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:PATH
docker compose -p day6_student_starter -f starter/docker-compose.yml up -d --wait postgres
docker compose -p day6_student_starter -f starter/docker-compose.yml build pipeline
docker compose -p day6_student_starter -f starter/docker-compose.yml run --rm pipeline python scripts/check_setup.py
docker compose -p day6_student_starter -f starter/docker-compose.yml run --rm pipeline python -m unittest discover -s tests -v
```

Kết quả dev/test hiện đã chốt. Để tái lập trên cùng bộ test đã biết, dùng thư mục output riêng; pipeline chặn ghi lại dev vào `results/` sau khi đã có trace test:

```powershell
docker compose -p day6_student_starter -f starter/docker-compose.yml run --rm pipeline python -m src.run --output ../results/reproduction --split dev
docker compose -p day6_student_starter -f starter/docker-compose.yml run --rm pipeline python -m src.run --output ../results/reproduction --split test
```

Đổi thư mục output không biến bộ test đã xem thành holdout mới. Model chạy local, không cần API key; lần đầu cần mạng tải image/thư viện/model. Khi mạng chậm, có thể dùng `python starter/scripts/prefetch_model.py` và `python starter/scripts/prefetch_wheels.py`; Dockerfile tự dùng wheelhouse khi có marker COMPLETE. Cache model và wheel được gitignore.

Tái tạo corpus từ PDF riêng tư và tham số đã lưu: `docker compose -p day6_student_starter -f starter/docker-compose.yml run --rm pipeline python scripts/rebuild_corpus.py`. Xem [data/README.md](../../data/README.md) về nguồn, metadata và cách chọn trang; [benchmark/README.md](../../benchmark/README.md) về gold/câu hỏi.

Sau khi sửa nhãn, chạy `python starter/scripts/summarize_audit.py --sync` để tổng hợp báo cáo. Dừng dịch vụ bằng `docker compose -p day6_student_starter -f starter/docker-compose.yml stop`; giữ volume PostgreSQL để bảo toàn dữ liệu.
