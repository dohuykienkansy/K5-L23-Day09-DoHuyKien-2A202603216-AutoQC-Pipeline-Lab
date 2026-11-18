"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    issues = []
    lf_cfg = cfg["label_format"]

    for lf in ds.label_files():
        stem = lf.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        valid_boxes = []
        img_size = ds.image_size(stem)

        for lineno, raw in lines:
            raw_stripped = raw.strip()
            if not raw_stripped:
                continue

            try:
                cls_id, cx, cy, w, h = parse_yolo_line(raw_stripped)
            except ValueError:
                issues.append(
                    Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng sai định dạng: {raw_stripped}", line=lineno)
                )
                continue

            if cls_id < 0 or cls_id >= len(ds.classes):
                issues.append(
                    Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls_id} không hợp lệ", line=lineno)
                )
                continue

            if w <= 0 or h <= 0:
                issues.append(
                    Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước <= 0 (w={w}, h={h})", line=lineno)
                )
                continue

            # BOX_OUT_OF_IMAGE: mép trái = cx - w/2, mép phải = cx + w/2
            left, right = cx - w / 2, cx + w / 2
            top, bottom = cy - h / 2, cy + h / 2
            overflow = max(0.0, -left, right - 1.0, -top, bottom - 1.0)
            if overflow > lf_cfg["overflow_tol"]:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "BOX_OUT_OF_IMAGE",
                        stem,
                        f"box tràn mép ảnh (overflow={overflow:.4f})",
                        line=lineno,
                        extra={"overflow": overflow},
                    )
                )
                # KHÔNG continue — vẫn kiểm tiếp DUP_BOX và WARN

            # DUP_BOX: so với các dòng hợp lệ trước đó cùng lớp
            is_dup = False
            for prev_cls, prev_box in valid_boxes:
                if prev_cls == cls_id and iou_xywh((cx, cy, w, h), prev_box) > lf_cfg["dup_box_iou"]:
                    issues.append(
                        Issue(
                            "label_format",
                            ERROR,
                            "DUP_BOX",
                            stem,
                            f"trùng box với dòng trước đó (cùng lớp {cls_id})",
                            line=lineno,
                        )
                    )
                    is_dup = True
                    break

            if not is_dup:
                valid_boxes.append((cls_id, (cx, cy, w, h)))

            # BOX_TINY (pixels): cạnh ngắn < min_box_px
            if img_size:
                W, H = img_size
                short_side_px = min(w * W, h * H)
                if short_side_px < lf_cfg["min_box_px"]:
                    issues.append(
                        Issue(
                            "label_format",
                            WARN,
                            "BOX_TINY",
                            stem,
                            f"cạnh ngắn của box ({short_side_px:.1f}px) < {lf_cfg['min_box_px']}px",
                            line=lineno,
                        )
                    )

            # BOX_HUGE: diện tích phần trăm > max_box_frac
            if w * h > lf_cfg["max_box_frac"]:
                issues.append(
                    Issue(
                        "label_format",
                        WARN,
                        "BOX_HUGE",
                        stem,
                        f"diện tích box ({w * h:.3f}) > {lf_cfg['max_box_frac']}",
                        line=lineno,
                    )
                )

    return issues
