"""Steps Recorder — ghi lại thao tác người dùng thành tài liệu hướng dẫn.

Gói này giữ phần lõi không phụ thuộc GUI ở các module con (models, config,
ai, recorder, exporters, element); giao diện Tkinter nằm trong steps_recorder.gui.
Các tên public được re-export tại đây để dùng tiện: `from steps_recorder import Step`.
"""
from .ai import (apply_ai_result, build_ai_messages, call_ai, parse_ai_content)
from .config import CONFIG_FILETYPES, CONFIG_PATH, PRESETS, AppConfig
from .element import describe_element_at, friendly_element_label
from .models import (PROJECT_FILETYPES, PROJECT_FORMAT, PROJECT_VERSION, Step)
from .recorder import (HOTKEY_IGNORED_KEYS, MASKED_TEXT_ACTION, StepsRecorder,
                       format_typed_action, is_double_click, pick_monitor)

__all__ = [
    "AppConfig", "CONFIG_FILETYPES", "CONFIG_PATH", "PRESETS",
    "PROJECT_FILETYPES", "PROJECT_FORMAT", "PROJECT_VERSION", "Step",
    "HOTKEY_IGNORED_KEYS", "MASKED_TEXT_ACTION", "StepsRecorder",
    "format_typed_action", "is_double_click", "pick_monitor",
    "apply_ai_result", "build_ai_messages", "call_ai", "parse_ai_content",
    "describe_element_at", "friendly_element_label",
]
