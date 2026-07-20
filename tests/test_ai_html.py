import pytest

from steps_recorder import AppConfig, Step
from steps_recorder.ai import build_html_messages, extract_html, render_ai_html


def _steps():
    return [
        Step(index=1, timestamp="t1", action="Mở app", window="App",
             images=["AAA", "BBB"]),
        Step(index=2, timestamp="t2", action="Nhấn nút", window="App"),
    ]


class TestExtractHtml:
    def test_plain_document(self):
        html = "<!DOCTYPE html><html><body>x</body></html>"
        assert extract_html(html) == html

    def test_fenced_document(self):
        out = extract_html("```html\n<!DOCTYPE html><html></html>\n```")
        assert out.startswith("<!DOCTYPE html>")

    def test_prose_before_and_after(self):
        out = extract_html(
            "Đây là kết quả:\n<!DOCTYPE html><html><body>x</body></html>\nHết.")
        assert out.startswith("<!DOCTYPE html>")
        assert out.endswith("</html>")

    def test_no_html_raises(self):
        with pytest.raises(RuntimeError):
            extract_html("chỉ là văn bản thường")


class TestRenderAiHtml:
    def test_placeholder_replaced_with_data_uri(self):
        html = "<html><body>{{IMG_1_1}}</body></html>"
        out = render_ai_html(html, _steps())
        assert "data:image/png;base64,AAA" in out
        assert "{{IMG_1_1}}" not in out

    def test_placeholder_with_spaces(self):
        out = render_ai_html("<html><body>{{ IMG_1_2 }}</body></html>", _steps())
        assert "data:image/png;base64,BBB" in out

    def test_unknown_placeholder_removed(self):
        out = render_ai_html("<html><body>{{IMG_9_9}}</body></html>", _steps())
        assert "{{IMG_9_9}}" not in out
        assert "IMG_9_9" not in out

    def test_unused_images_go_to_appendix(self):
        out = render_ai_html("<html><body>{{IMG_1_1}}</body></html>", _steps())
        # ảnh 1_2 không được AI đặt -> phải nằm trong phụ lục trước </body>
        assert "Phụ lục ảnh" in out
        assert "data:image/png;base64,BBB" in out
        assert out.index("Phụ lục ảnh") < out.index("</body>")

    def test_no_appendix_when_all_used(self):
        html = "<html><body>{{IMG_1_1}}{{IMG_1_2}}</body></html>"
        out = render_ai_html(html, _steps())
        assert "Phụ lục ảnh" not in out


class TestBuildHtmlMessages:
    def test_lists_only_real_placeholders(self):
        msgs = build_html_messages(_steps(), AppConfig())
        user = msgs[1]["content"]
        assert "{{IMG_1_1}}" in user and "{{IMG_1_2}}" in user
        assert "{{IMG_2_1}}" not in user  # bước 2 không có ảnh

    def test_includes_existing_title_and_summary(self):
        msgs = build_html_messages(_steps(), AppConfig(),
                                   title="Tài liệu X", summary="Tóm tắt Y")
        user = msgs[1]["content"]
        assert "Tài liệu X" in user and "Tóm tắt Y" in user

    def test_system_prompt_forbids_img_tags(self):
        msgs = build_html_messages(_steps(), AppConfig())
        assert "KHÔNG tự viết thẻ <img>" in msgs[0]["content"]


def test_config_auto_process_default_off():
    assert AppConfig().auto_process is False
