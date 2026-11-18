"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_BOX_CODES = {"BOX_OUT_OF_IMAGE"}


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]

    # 1. Xoá ảnh + nhãn đối với các lỗi ảnh (remove_image)
    removed_stems = set()
    for i in errors:
        if i.code in REMOVE_IMAGE_CODES:
            if i.image not in removed_stems:
                removed_stems.add(i.image)
                im_path = ds.image_path(i.image)
                if im_path and im_path.exists():
                    im_path.unlink()
                lab_path = ds.label_path(i.image)
                if lab_path and lab_path.exists():
                    lab_path.unlink()
                if hasattr(ds, "_size_cache"):
                    ds._size_cache.pop(i.image, None)
                fixes.append({
                    "image": i.image,
                    "line": "",
                    "action": "remove_image",
                    "before": "ảnh + nhãn",
                    "after": "(đã xoá)",
                })

    # 2. Sửa BAD_CLASS_NAME trong data.yaml (rename_classes)
    if any(i.code == "BAD_CLASS_NAME" for i in errors) and ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        old_names = d.get("names", {})
        d["names"] = dict(enumerate(cfg["classes"]))
        ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        fixes.append({
            "image": "data.yaml",
            "line": "",
            "action": "rename_classes",
            "before": str(old_names),
            "after": str(dict(enumerate(cfg["classes"]))),
        })

    # 3. Ghi nhận MISSING_LABEL_FILE (needs_label) — không tạo file
    needs_label_stems = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed_stems:
            if i.image not in needs_label_stems:
                needs_label_stems.add(i.image)
                fixes.append({
                    "image": i.image,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Gom các lỗi cấp dòng theo file nhãn (bỏ qua ảnh đã bị xoá)
    file_issues = defaultdict(list)
    for i in errors:
        if i.image not in removed_stems and i.code in (DROP_LINE_CODES | CLIP_BOX_CODES):
            if isinstance(i.line, int):
                file_issues[i.image].append(i)

    # 5. Xử lý từng file nhãn: sửa dòng và ghi lại MỘT lần duy nhất
    for stem in sorted(file_issues.keys()):
        lab_path = ds.label_path(stem)
        if not lab_path.exists():
            continue

        raw_lines = lab_path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_to_issues = defaultdict(list)
        for iss in file_issues[stem]:
            line_to_issues[iss.line].append(iss)

        dropped_lines = set()
        modified_lines = {}
        file_fixes = []

        for lineno in sorted(line_to_issues.keys()):
            if not (1 <= lineno <= len(raw_lines)):
                continue

            raw = raw_lines[lineno - 1]
            codes_on_line = {iss.code for iss in line_to_issues[lineno]}

            # Ưu tiên: nếu có bất kỳ lỗi drop_line nào -> xoá dòng
            if codes_on_line & DROP_LINE_CODES:
                dropped_lines.add(lineno)
                file_fixes.append({
                    "image": stem,
                    "line": lineno,
                    "action": "drop_line",
                    "before": raw,
                    "after": "",
                })
            elif "BOX_OUT_OF_IMAGE" in codes_on_line:
                # Cắt box về [0, 1]
                try:
                    cls_id, cx, cy, w, h = parse_yolo_line(raw.strip())
                except Exception:
                    dropped_lines.add(lineno)
                    file_fixes.append({
                        "image": stem,
                        "line": lineno,
                        "action": "drop_line",
                        "before": raw,
                        "after": "",
                    })
                    continue

                left = cx - w / 2
                right = cx + w / 2
                top = cy - h / 2
                bottom = cy + h / 2

                left_c = max(0.0, min(1.0, left))
                right_c = max(0.0, min(1.0, right))
                top_c = max(0.0, min(1.0, top))
                bottom_c = max(0.0, min(1.0, bottom))

                new_w = right_c - left_c
                new_h = bottom_c - top_c

                if new_w <= 0.0 or new_h <= 0.0:
                    # Box nằm hoàn toàn ngoài ảnh -> chuyển thành drop_line
                    dropped_lines.add(lineno)
                    file_fixes.append({
                        "image": stem,
                        "line": lineno,
                        "action": "drop_line",
                        "before": raw,
                        "after": "",
                    })
                else:
                    new_cx = (left_c + right_c) / 2
                    new_cy = (top_c + bottom_c) / 2
                    new_line = f"{int(cls_id)} {round(new_cx, 6)} {round(new_cy, 6)} {round(new_w, 6)} {round(new_h, 6)}"
                    modified_lines[lineno] = new_line
                    file_fixes.append({
                        "image": stem,
                        "line": lineno,
                        "action": "clip_box",
                        "before": raw,
                        "after": new_line,
                    })

        # Xây dựng lại các dòng sau khi sửa
        new_file_lines = []
        for idx, line_text in enumerate(raw_lines, start=1):
            if idx in dropped_lines:
                continue
            if idx in modified_lines:
                new_file_lines.append(modified_lines[idx])
            else:
                new_file_lines.append(line_text)

        content = "\n".join(new_file_lines) + ("\n" if new_file_lines else "")
        lab_path.write_text(content, encoding="utf-8")
        fixes.extend(file_fixes)

    return fixes
