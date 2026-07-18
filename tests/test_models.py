from steps_recorder import Step


def test_step_roundtrip():
    s = Step(index=3, timestamp="2026-01-01 10:00:00", action="Nhấp chuột",
             window="App", description="Mô tả", section="Phần 1",
             images=["abc", "def"])
    d = s.to_dict()
    s2 = Step.from_dict(d)
    assert s2 == s


def test_step_from_dict_missing_fields():
    s = Step.from_dict({})
    assert s.index == 0
    assert s.action == ""
    assert s.images == []


def test_step_from_dict_bad_images():
    s = Step.from_dict({"index": "5", "images": "not-a-list"})
    assert s.index == 5
    assert s.images == []


def test_step_from_dict_filters_empty_images():
    s = Step.from_dict({"images": ["a", "", None, "b"]})
    assert s.images == ["a", "b"]
