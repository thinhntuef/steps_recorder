import json

import steps_recorder.ai as ai_mod
from steps_recorder import AppConfig, Step
from steps_recorder.ai import (build_ai_messages, build_clarify_messages,
                               build_html_messages, call_ai_questions,
                               format_qa_block, parse_questions)


def _cfg():
    return AppConfig(base_url="http://localhost:8000/v1", model="m")


def _steps():
    return [Step(index=1, timestamp="t", action="Mở app", window="App")]


class TestParseQuestions:
    def test_valid_shape(self):
        out = parse_questions(json.dumps({"questions": [
            {"question": "Tài liệu cho ai?", "suggestions": ["Nội bộ", "Khách"]},
        ]}))
        assert out == [{"question": "Tài liệu cho ai?",
                        "suggestions": ["Nội bộ", "Khách"]}]

    def test_fenced_and_prose(self):
        out = parse_questions('Đây là JSON:\n```json\n{"questions": '
                              '[{"question": "Q1"}]}\n```')
        assert out[0]["question"] == "Q1"
        assert out[0]["suggestions"] == []

    def test_bare_list_and_string_items(self):
        out = parse_questions('["Câu A", {"q": "Câu B"}]')
        assert [q["question"] for q in out] == ["Câu A", "Câu B"]

    def test_empty_and_garbage_return_empty(self):
        assert parse_questions('{"questions": []}') == []
        assert parse_questions("không phải json") == []
        assert parse_questions("") == []

    def test_caps_number_of_questions(self):
        many = {"questions": [{"question": f"Q{i}"} for i in range(10)]}
        assert len(parse_questions(json.dumps(many))) == ai_mod.MAX_QUESTIONS_PER_ROUND


class TestQaBlock:
    def test_empty_qa_no_block(self):
        assert format_qa_block([]) == ""

    def test_block_contains_pairs(self):
        block = format_qa_block([("Cho ai?", "Khách hàng")])
        assert "Hỏi: Cho ai?" in block and "Đáp: Khách hàng" in block

    def test_qa_flows_into_compile_messages(self):
        msgs = build_ai_messages(_steps(), _cfg(), qa=[("Cho ai?", "Khách")])
        assert "GIẢI ĐÁP LÀM RÕ" in msgs[1]["content"]
        assert "Đáp: Khách" in msgs[1]["content"]

    def test_qa_flows_into_html_messages(self):
        msgs = build_html_messages(_steps(), _cfg(), qa=[("Cho ai?", "Khách")])
        assert "Đáp: Khách" in msgs[1]["content"]

    def test_no_qa_no_block_in_messages(self):
        msgs = build_ai_messages(_steps(), _cfg())
        assert "GIẢI ĐÁP LÀM RÕ" not in msgs[1]["content"]


class TestCallAiQuestions:
    def test_returns_parsed_questions(self, monkeypatch):
        monkeypatch.setattr(
            ai_mod, "_chat_completion",
            lambda *a, **k: '{"questions": [{"question": "Q?"}]}')
        out = call_ai_questions(_cfg(), _steps())
        assert out[0]["question"] == "Q?"

    def test_no_steps_returns_empty_without_call(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("không được gọi API")
        monkeypatch.setattr(ai_mod, "_chat_completion", boom)
        assert call_ai_questions(_cfg(), []) == []

    def test_previous_answers_included_in_prompt(self):
        msgs = build_clarify_messages(_steps(), _cfg(),
                                      qa=[("Q cũ?", "Đáp cũ")])
        assert "Đáp cũ" in msgs[1]["content"]
        assert "còn gì chưa rõ nữa không" in msgs[1]["content"]
