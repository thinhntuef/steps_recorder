import base64
import io

from PIL import Image

from steps_recorder import (MASKED_TEXT_ACTION, Step, StepsRecorder,
                            format_typed_action, is_double_click, pick_monitor)

MONITORS = [
    {"left": -1920, "top": 0, "width": 3840, "height": 1080},   # [0] khung ảo
    {"left": 0, "top": 0, "width": 1920, "height": 1080},       # màn chính
    {"left": -1920, "top": 0, "width": 1920, "height": 1080},   # màn bên trái
]


class TestPickMonitor:
    def test_point_on_primary(self):
        assert pick_monitor(MONITORS, 100, 200) is MONITORS[1]

    def test_point_on_negative_left_monitor(self):
        assert pick_monitor(MONITORS, -500, 500) is MONITORS[2]

    def test_point_outside_falls_back_to_primary(self):
        assert pick_monitor(MONITORS, 99999, 99999) is MONITORS[1]

    def test_edge_belongs_to_containing_monitor(self):
        assert pick_monitor(MONITORS, 1919, 1079) is MONITORS[1]
        assert pick_monitor(MONITORS, 1920, 0) is MONITORS[1]  # ngoài -> chính


class TestMaskTypedText:
    def test_masked_hides_content(self):
        label = format_typed_action("mật khẩu bí mật", masked=True)
        assert "mật khẩu" not in label
        assert label == MASKED_TEXT_ACTION

    def test_unmasked_keeps_old_format(self):
        assert format_typed_action("abc", masked=False) == 'Nhập văn bản: "abc"'

    def test_flush_keys_respects_mask(self):
        rec = StepsRecorder()
        rec.mask_typed_text = True
        rec._key_buffer.extend("secret")
        rec._key_buffer_window = "App"
        rec._flush_keys()
        assert rec.steps[0].action == MASKED_TEXT_ACTION
        assert "secret" not in rec.steps[0].action

    def test_flush_keys_unmasked(self):
        rec = StepsRecorder()
        rec.mask_typed_text = False
        rec._key_buffer.extend("abc")
        rec._key_buffer_window = "App"
        rec._flush_keys()
        assert rec.steps[0].action == 'Nhập văn bản: "abc"'


class TestDoubleClick:
    def test_same_button_close_in_time_and_space(self):
        assert is_double_click((10.0, 100, 100, "Button.left"),
                               10.3, 103, 99, "Button.left")

    def test_too_slow(self):
        assert not is_double_click((10.0, 100, 100, "Button.left"),
                                   10.5, 100, 100, "Button.left")

    def test_too_far(self):
        assert not is_double_click((10.0, 100, 100, "Button.left"),
                                   10.1, 120, 100, "Button.left")

    def test_different_button(self):
        assert not is_double_click((10.0, 100, 100, "Button.left"),
                                   10.1, 100, 100, "Button.right")

    def test_no_previous_click(self):
        assert not is_double_click(None, 10.0, 100, 100, "Button.left")


def _tiny_png_b64():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestExportMarkdown:
    def _recorder(self):
        rec = StepsRecorder()
        rec.report_title = "Hướng dẫn thử"
        rec.report_summary = "Tóm tắt ngắn."
        rec.steps = [
            Step(index=1, timestamp="t1", action="Mở ứng dụng", window="App",
                 description="Chi tiết bước 1", section="Phần 1",
                 images=[_tiny_png_b64()]),
            Step(index=2, timestamp="t2", action=MASKED_TEXT_ACTION,
                 window="(không xác định)", section="Phần 2"),
        ]
        return rec

    def test_export_creates_md_and_assets(self, tmp_path):
        rec = self._recorder()
        out = rec.export_markdown(str(tmp_path / "guide.md"))
        text = open(out, encoding="utf-8").read()
        assert "# Hướng dẫn thử" in text
        assert "## Phần 1" in text
        assert "### Bước 1: Mở ứng dụng" in text
        assert "guide_assets/step_1_1.png" in text
        assert (tmp_path / "guide_assets" / "step_1_1.png").is_file()
        # cửa sổ "(không xác định)" không được in ra
        assert "(không xác định)" not in text

    def test_export_without_images_creates_no_assets_dir(self, tmp_path):
        rec = self._recorder()
        for s in rec.steps:
            s.images = []
        rec.export_markdown(str(tmp_path / "guide.md"))
        assert not (tmp_path / "guide_assets").exists()
