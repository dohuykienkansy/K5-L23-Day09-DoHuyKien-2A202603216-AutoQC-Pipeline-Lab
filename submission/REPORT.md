# Báo cáo Day 09 — Đỗ Huy Kiên, 2A202603216

## 1. Kết luận trước

Pipeline kết luận **Hold** (mã thoát 10).

- **Đầu vào:** 224 ảnh thô (`data/raw/`).
- **Sau intake:** Giữ lại **205 ảnh**, loại bỏ 19 ảnh (hỏng, quá nhỏ, trùng lặp byte/phash, rò rỉ test).
- **Lỗi ERROR còn lại sau sửa và duyệt:** 0 lỗi bắt buộc.
- **Tỉ lệ ảnh có cảnh báo (WARN) chưa duyệt:** 45/205 = **21.95%** (vượt ngưỡng Hold 10.00%).
- **Lý do chính:** Sau khi hoàn thành autofix các lỗi cú pháp và cho người duyệt tối đa 80 ảnh theo ngân sách, lô dữ liệu vẫn còn 45 ảnh chứa cảnh báo ngữ nghĩa (`POSSIBLE_*`) chưa được kiểm tra. Do đó, pipeline xuất dataset ra `submission/export/clean_v1/` dưới dạng **bản nháp** (Hold) để thử nghiệm nội bộ chứ chưa đủ điều kiện phát hành chính thức (Release).

## 2. Lỗi và phân việc

Thống kê từ `02_error_list_v1.txt` trên lô 205 ảnh sau intake:

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `DUP_BOX` | 7 dòng | Máy (`drop_line`) | Box trùng lặp vị trí cùng lớp — vi phạm cú pháp rõ ràng, xoá an toàn. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (`clip_box`) | Mép box tràn ngoài [0, 1] — máy cắt về biên an toàn, giữ lại box nếu còn diện tích. |
| `BAD_CLASS_ID` | 6 dòng | Máy (`drop_line`) | ID lớp ngoài dải [0, 3] (như id 93, 7, -1, 4) — sai quy tắc cơ bản. |
| `BOX_ZERO` | 4 dòng | Máy (`drop_line`) | Chiều rộng hoặc chiều cao ≤ 0 (box rỗng) — không mang thông tin. |
| `BAD_FORMAT` | 3 dòng | Máy (`drop_line`) | Dòng nhãn chứa giá trị `nan` hoặc thiếu toạ độ — không thể parse thành box. |
| `BAD_CLASS_NAME` | 2 dòng | Máy (`rename_classes`) | Tên lớp sai quy cách ('Person', 'Bus') — máy đổi về alias chuẩn trong `data.yaml`. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (`needs_label`) | Máy không thể tự bịa toạ độ nhãn; bắt buộc người gán phải bổ sung từ đầu. |
| `POSSIBLE_MISSING` | 68 ảnh | Người (hàng đợi) | Model yolo26l phát hiện vật mà nhãn chưa có — cần mắt người xác nhận có bỏ sót không. |
| `POSSIBLE_WRONG_CLASS` | 19 ảnh | Người (hàng đợi) | Nghi ngờ nhầm lẫn giữa car ↔ truck ↔ bus — cần người phân biệt ngữ nghĩa. |
| `POSSIBLE_FALSE_POS` | 25 ảnh | Người (hàng đợi) | Nhãn có box nhưng model không thấy vật — có thể gán thừa hoặc model bị khuất. |
| `POSSIBLE_LOOSE_BOX` | 31 ảnh | Người (hàng đợi) | Box đúng lớp nhưng IoU < 0.5 — cần người căn chỉnh lại biên cho sát vật. |

**Cơ chế xếp hàng đợi `05_review_queue.csv`:**
Ảnh được chấm điểm ưu tiên theo trọng số trong `configs/pipeline.yaml`. Ảnh `NEEDS_LABEL` có trọng số cao nhất (10) vì thiếu nhãn hoàn toàn là lỗi nghiêm trọng nhất. Tiếp theo là các ảnh kết hợp nhiều lỗi nặng (`FIXED_DROP_LINE` trọng số 2, `POSSIBLE_WRONG_CLASS` trọng số 3, `POSSIBLE_MISSING` trọng số 2) như `img_0020` (14.528 điểm) và `img_0185` (10.052 điểm).
Với ngân sách 80 ảnh, người duyệt mô phỏng đã xử lý:
- 100% (6/6) ảnh thiếu file nhãn `NEEDS_LABEL`.
- 100% (19/19) ca nghi ngờ nhầm lớp `POSSIBLE_WRONG_CLASS`.
- 54 ca `POSSIBLE_MISSING`, 12 ca `POSSIBLE_FALSE_POS`, 7 ca `POSSIBLE_LOOSE_BOX` và 11 ca `EMPTY_LABEL`.
Tổng cộng người duyệt đã giải quyết 92 lượt cảnh báo ngữ nghĩa quan trọng nhất trước khi cạn ngân sách 80 ảnh.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **4** | P=1.00 / R=0.50 → P=1.00 / R=0.67 | Ưu tiên Precision tuyệt đối (1.00) để không xoá nhầm ảnh sạch; nâng từ 2 lên 4 giúp Recall tăng từ 0.50 lên 0.67 (bắt thêm ảnh trùng gần đúng). Từ 4 lên 5, 6 metric không đổi nên 4 là điểm bẻ gãy tối ưu. |
| `second_opinion.conf` | 0.25 | **0.5** | P=0.50 / R=1.00 → P=0.57 / R=1.00 (ở `POSSIBLE_MISSING`) | Giữ Recall ở mức 1.00 để không bỏ sót vật thể; Precision tăng từ 0.50 lên 0.57 giúp giảm bớt báo động giả vào hàng đợi người. Không chọn conf ≥ 0.7 vì Recall bắt đầu sụt giảm còn 0.88. |

**Điểm calibration có thể đánh lừa:**
Tập `data/calib/` chỉ có 39 ảnh với số lượng lỗi chèn rất ít (chỉ 6 ca `DUP_IMAGE_NEAR`, 8 ca `POSSIBLE_MISSING`), dẫn đến việc mỗi mẫu đúng/sai làm thay đổi Precision/Recall theo các bước nhảy rất lớn (12.5% – 16.7%), dễ gây cảm giác tối ưu giả tạo.
Thực tế khi kiểm tra trên lô `data/raw/` 224 ảnh:
- Mở xem 2 cặp ảnh bị gắn cờ `DUP_IMAGE_NEAR` với `phash_dist=4`: `img_0076` (640×427) trùng với `img_0042` (576×384) và `img_0143` (576×384) trùng với `img_0037` (640×427). Đây chính xác là cùng một khung cảnh bị thu nhỏ (resize 90%), khoảng cách phash đo được bằng 0. Việc loại bỏ 2 ảnh này ở intake là hoàn toàn chính xác, chứng minh ngưỡng 4 hoạt động tốt trên dữ liệu thật mà không loại nhầm ảnh khác.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Chứng minh Gate chặn đúng:**
Em đã chạy thử nghiệm mô phỏng tình huống không có người duyệt (`--budget 0`):
```bash
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
- Kết quả: Khi ngân sách duyệt bằng 0, cả 6 ảnh `MISSING_LABEL_FILE` không được xử lý, tồn đọng 6 lỗi ERROR ở vòng QC v3.
- Kết luận: **Rework**, mã thoát trả về là **20**.
- Kiểm tra thư mục `work/exp_nb/`: **0 file** được tạo ra (pipeline chặn hoàn toàn việc xuất dataset khi còn lỗi bắt buộc).

**(b) Hai điểm mù pipeline không bắt được:**
1. **Model kiểm tra (yolo26l) và nhãn cùng mắc chung một lỗi:** Nếu cả người gán nhãn lẫn model yolo26l đều bỏ sót một vật thể nhỏ hoặc bị khuất (occluded object), `POSSIBLE_MISSING` sẽ không được kích hoạt vì model không sinh ra dự đoán đủ tin cậy (conf < 0.5). Tương tự, nếu cả hai cùng nhận diện nhầm một xe bán tải thành `car` thay vì `truck` với IoU > 0.5, pipeline coi như khớp đúng và bỏ qua.
2. **Box lỏng nhẹ rơi vào vùng mù ngưỡng IoU:** Cảnh báo `POSSIBLE_LOOSE_BOX` chỉ kích hoạt khi IoU < `iou_loose` (0.5). Nếu một nhãn vẽ quá rộng hoặc lệch mép nhưng IoU với dự đoán chuẩn vẫn đạt trong khoảng 0.51 – 0.65, pipeline xem như là box đạt chuẩn (`iou >= 0.5`) và không đưa ra cảnh báo nào, để lọt box kém chất lượng vào tập huấn luyện.

## 5. Train: raw vs clean (tùy chọn)

Chưa chạy — môi trường máy cục bộ không có GPU, phần train Colab là tùy chọn nên em tạm thời bỏ qua để ưu tiên hoàn thiện chắc chắn phần lõi của pipeline.

Giả thuyết phân tích nếu tiến hành train:
- Trong tập `raw` có 4 ảnh rò rỉ trực tiếp từ tập test (`img_0049`, `img_0167`, `img_0174`, `img_0221` trùng byte với test set). Nếu train trên `raw`, metric mAP50 trên test set có thể bị thổi phồng nhân tạo do model đã "học thuộc" ảnh test.
- Với kích thước tập test chỉ 100 ảnh và số lượt train ít (2 seed), phương sai ngẫu nhiên giữa các seed thường dao động 1% – 2%. Nếu chênh lệch mAP50 giữa `clean` và `raw` nhỏ hơn độ lệch chuẩn này thì về mặt khoa học chưa thể kết luận `clean` tốt hơn `raw`.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Hold**
Lô dữ liệu xuất ở `submission/export/clean_v1/` hiện là bản nháp nội bộ. Để lô đạt quyết định **Release**, cần:
- Tăng ngân sách người duyệt thêm khoảng 40–50 ảnh để xử lý 45 ảnh còn cảnh báo ngữ nghĩa, hạ tỉ lệ cảnh báo xuống dưới 10%.
- Người gán nhãn hoàn thiện việc vẽ box cho 6 ảnh `MISSING_LABEL_FILE`.

**(b) Ghi chú sử dụng AI:**
- **Prompt chính:** Em dán docstring từ stub của từng module, kèm 1 test case mẫu trong thư mục `tests/` và cấu trúc `Dataset` trong `pipeline/common.py`. Em yêu cầu AI viết đúng logic nghiệp vụ, đọc toàn bộ tham số từ `cfg`, không được hardcode ngưỡng và không được nuốt lỗi ngoại lệ.
- **Cách em kiểm tra code:** Em chạy `pytest` riêng cho từng module (`pytest tests/test_<module>.py -q`), mở đọc lướt code để đảm bảo không có lệnh can thiệp vào `data/raw` hay file cấu hình cố định, sau đó chạy toàn bộ 79 tests và kiểm tra chéo trên tập `calib`.
- **1 lần AI sai và cách em xử lý:** Ở module `label_format.py` và `autofix.py`, ban đầu AI tự tiện dùng `enumerate(lines, start=1)` để đánh lại số dòng, dẫn đến việc xoá dòng bị lệch vị trí gốc do file nhãn có các dòng trống. Em đọc traceback từ test, chỉ ra rằng `ds.read_label_lines()` đã trả về sẵn cặp `(lineno, raw)` và yêu cầu AI sửa lại để giữ nguyên số dòng thực tế.
