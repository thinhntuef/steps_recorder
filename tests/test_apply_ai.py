from steps_recorder import Step, StepsRecorder, apply_ai_result


def _recorder_with_steps(n=3):
    rec = StepsRecorder()
    for i in range(1, n + 1):
        rec.steps.append(Step(
            index=i, timestamp=f"2026-01-01 10:00:0{i}",
            action=f"Hành động {i}", window=f"Cửa sổ {i}",
            images=[f"img{i}"]))
    return rec


def test_apply_merge_concatenates_images_and_renumbers():
    rec = _recorder_with_steps(3)
    apply_ai_result(rec, {
        "title": "Tiêu đề mới", "summary": "Tóm tắt mới",
        "steps": [
            {"source_indexes": [1, 2], "label": "Gộp 1+2",
             "description": "Mô tả gộp", "section": "Phần A"},
            {"source_indexes": [3], "label": "Bước 3 mới",
             "description": "", "section": "Phần B"},
        ],
    }, merge=True)
    assert len(rec.steps) == 2
    assert rec.steps[0].index == 1
    assert rec.steps[0].action == "Gộp 1+2"
    assert rec.steps[0].images == ["img1", "img2"]
    assert rec.steps[1].index == 2
    assert rec.report_title == "Tiêu đề mới"
    assert rec.report_summary == "Tóm tắt mới"


def test_apply_merge_drops_unknown_indexes():
    rec = _recorder_with_steps(2)
    apply_ai_result(rec, {"steps": [
        {"source_indexes": [1, 99], "label": "OK"},
        {"source_indexes": [42], "label": "Bị bỏ"},
    ]}, merge=True)
    assert len(rec.steps) == 1
    assert rec.steps[0].images == ["img1"]


def test_apply_merge_empty_rebuild_keeps_steps():
    rec = _recorder_with_steps(2)
    apply_ai_result(rec, {"steps": [{"source_indexes": [99], "label": "X"}]},
                    merge=True)
    assert len(rec.steps) == 2  # dựng lại rỗng -> giữ nguyên (an toàn)


def test_apply_one_to_one_updates_by_index():
    rec = _recorder_with_steps(2)
    apply_ai_result(rec, {"steps": [
        {"index": 2, "label": "Nhãn mới", "description": "Mô tả mới",
         "section": "Phần C"},
    ]}, merge=False)
    assert rec.steps[0].action == "Hành động 1"  # không đổi
    assert rec.steps[1].action == "Nhãn mới"
    assert rec.steps[1].description == "Mô tả mới"
    assert rec.steps[1].section == "Phần C"


def test_apply_one_to_one_empty_label_keeps_old():
    rec = _recorder_with_steps(1)
    apply_ai_result(rec, {"steps": [{"index": 1, "label": "", "description": ""}]},
                    merge=False)
    assert rec.steps[0].action == "Hành động 1"
