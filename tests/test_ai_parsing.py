import json

import pytest

from steps_recorder import _normalize_ai, _strip_fences, parse_ai_content


def test_strip_fences_plain_text():
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_json_fence():
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_fence_no_language():
    assert _strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_parse_valid_json():
    out = parse_ai_content(json.dumps({
        "title": "HDSD", "summary": "Tóm tắt",
        "steps": [{"index": 1, "label": "Mở app", "description": "Chi tiết",
                   "section": "Bắt đầu"}],
    }))
    assert out["title"] == "HDSD"
    assert out["steps"][0]["label"] == "Mở app"
    assert out["steps"][0]["section"] == "Bắt đầu"


def test_parse_fenced_json():
    out = parse_ai_content('```json\n{"title": "T", "steps": []}\n```')
    assert out["title"] == "T"


def test_parse_json_embedded_in_prose():
    out = parse_ai_content('Đây là kết quả:\n{"title": "T", "steps": []}\nHết.')
    assert out["title"] == "T"


def test_parse_sections_shape_flattened():
    out = parse_ai_content(json.dumps({
        "title": "T",
        "sections": [
            {"title": "Phần 1", "steps": [{"index": 1, "label": "B1"}]},
            {"title": "Phần 2", "steps": [{"index": 2, "label": "B2"}]},
        ],
    }))
    assert [s["section"] for s in out["steps"]] == ["Phần 1", "Phần 2"]


def test_parse_garbage_raises():
    with pytest.raises(RuntimeError):
        parse_ai_content("không phải json")


def test_normalize_ai_rejects_non_dict():
    with pytest.raises(ValueError):
        _normalize_ai([1, 2, 3])


def test_normalize_coerces_source_indexes():
    out = _normalize_ai({"steps": [
        {"index": "2", "source_indexes": ["1", 2, "x", None]},
    ]})
    assert out["steps"][0]["index"] == 2
    assert out["steps"][0]["source_indexes"] == [1, 2]
