import sys

from steps_recorder import describe_element_at, friendly_element_label


def test_label_button():
    assert friendly_element_label("Button", "Đăng nhập") == "nút 'Đăng nhập'"


def test_label_unknown_control_type_keeps_name():
    assert friendly_element_label("Whatever", "OK") == "'OK'"


def test_label_empty_name_returns_empty():
    assert friendly_element_label("Button", "") == ""
    assert friendly_element_label("Button", "   ") == ""


def test_label_collapses_whitespace():
    assert friendly_element_label("Edit", "Tên   người\ndùng") == "ô nhập 'Tên người dùng'"


def test_label_truncates_long_name():
    label = friendly_element_label("Button", "x" * 200)
    assert len(label) < 200
    assert label.endswith("…'")


def test_describe_returns_empty_off_windows():
    if sys.platform != "win32":
        assert describe_element_at(10, 10) == ""
