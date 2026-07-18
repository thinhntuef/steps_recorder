import urllib.request

import pytest

import steps_recorder.ai as ai_mod
from steps_recorder import AppConfig, Step
from steps_recorder.ai import (_chat_completion_meta, _request_timeout,
                               call_ai_html, merge_continuation)


def _cfg():
    return AppConfig(base_url="http://localhost:8000/v1", model="m")


def _steps():
    return [Step(index=1, timestamp="t", action="Mở app", window="App",
                 images=["AAA"])]


class TestMergeContinuation:
    def test_no_overlap_appends_all(self):
        assert merge_continuation("<html><body>", "<p>x</p>") == "<p>x</p>"

    def test_overlap_is_cut(self):
        prev = "<html><body><section class='step-one'>"
        nxt = "<section class='step-one'><p>tiếp</p>"
        assert merge_continuation(prev, nxt) == "<p>tiếp</p>"

    def test_short_accidental_overlap_not_cut(self):
        # trùng 1 ký tự '<' không được coi là lặp
        assert merge_continuation("abc<", "<div>") == "<div>"

    def test_fence_stripped_from_continuation(self):
        out = merge_continuation("<html>", "```html\n<body></body>\n```")
        assert out == "<body></body>"


class TestRequestTimeout:
    def test_default_and_floor(self):
        assert _request_timeout(AppConfig()) == 600
        assert _request_timeout(AppConfig(request_timeout=5)) == 30
        assert _request_timeout(AppConfig(request_timeout="abc")) == 600

    def test_timeout_becomes_clear_error(self, monkeypatch):
        def boom(*a, **k):
            raise TimeoutError()
        monkeypatch.setattr(urllib.request, "urlopen", boom)
        with pytest.raises(RuntimeError, match="Hết thời gian chờ AI"):
            _chat_completion_meta(_cfg(), [], use_response_format=False)


class TestHtmlLoop:
    def _patch_responses(self, monkeypatch, responses):
        """responses: list[(content, finish_reason)] trả về theo thứ tự gọi."""
        calls = {"n": 0, "messages_seen": []}

        def fake(cfg, messages, use_response_format, max_tokens=4096):
            calls["messages_seen"].append(list(messages))
            content, finish = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            return content, finish
        monkeypatch.setattr(ai_mod, "_chat_completion_meta", fake)
        return calls

    def test_single_round_when_complete(self, monkeypatch):
        calls = self._patch_responses(monkeypatch, [
            ("<!DOCTYPE html><html><body>{{IMG_1_1}}</body></html>", "stop"),
        ])
        out = call_ai_html(_cfg(), _steps())
        assert calls["n"] == 1
        assert "data:image/png;base64,AAA" in out

    def test_truncated_response_triggers_continuation(self, monkeypatch):
        calls = self._patch_responses(monkeypatch, [
            ("<!DOCTYPE html><html><body><h1>Tài liệu</h1>", "length"),
            ("<p>phần cuối</p></body></html>", "stop"),
        ])
        out = call_ai_html(_cfg(), _steps())
        assert calls["n"] == 2
        assert "<h1>Tài liệu</h1>" in out and "phần cuối" in out
        assert out.rstrip().endswith("</html>")
        # lượt 2 phải mang theo phần đã viết + yêu cầu viết tiếp
        second_messages = calls["messages_seen"][1]
        assert second_messages[-2]["role"] == "assistant"
        assert second_messages[-1]["role"] == "user"
        assert "VIẾT TIẾP" in second_messages[-1]["content"]

    def test_missing_close_tag_also_continues(self, monkeypatch):
        # finish=stop nhưng chưa có </html> -> vẫn phải lặp tiếp
        calls = self._patch_responses(monkeypatch, [
            ("<!DOCTYPE html><html><body>", "stop"),
            ("</body></html>", "stop"),
        ])
        call_ai_html(_cfg(), _steps())
        assert calls["n"] == 2

    def test_gives_up_after_max_rounds_and_self_closes(self, monkeypatch):
        calls = self._patch_responses(monkeypatch, [
            ("<!DOCTYPE html><html><body><p>mãi không xong</p>", "length"),
        ])
        out = call_ai_html(_cfg(), _steps())
        assert calls["n"] == ai_mod.MAX_HTML_ROUNDS
        assert "</html>" in out  # tự vá, không mất phần đã có
        assert "mãi không xong" in out

    def test_progress_callback_called_each_round(self, monkeypatch):
        self._patch_responses(monkeypatch, [
            ("<!DOCTYPE html><html><body>", "length"),
            ("</body></html>", "stop"),
        ])
        seen = []
        call_ai_html(_cfg(), _steps(),
                     on_progress=lambda r, m: seen.append((r, m)))
        assert seen == [(1, ai_mod.MAX_HTML_ROUNDS), (2, ai_mod.MAX_HTML_ROUNDS)]
