"""Nhận diện phần tử UI tại vị trí click (Windows, UI Automation qua pywinauto).

Cho nhãn bước dạng "Nhấp chuột trái vào nút 'Đăng nhập'" thay vì chỉ toạ độ.
Trên hệ không hỗ trợ (hoặc thiếu pywinauto) mọi hàm trả về chuỗi rỗng và
ứng dụng hoạt động như cũ.
"""
import logging
import sys
import threading

log = logging.getLogger("steps_recorder")

# Tên control UIA -> cách gọi tiếng Việt trong nhãn bước
CONTROL_NAMES_VI = {
    "Button": "nút",
    "SplitButton": "nút",
    "CheckBox": "hộp kiểm",
    "RadioButton": "nút chọn",
    "Edit": "ô nhập",
    "ComboBox": "hộp chọn",
    "MenuItem": "mục menu",
    "ListItem": "mục danh sách",
    "TreeItem": "mục cây thư mục",
    "TabItem": "thẻ",
    "Hyperlink": "liên kết",
    "Slider": "thanh trượt",
    "Document": "vùng văn bản",
    "Text": "chữ",
    "Image": "hình ảnh",
    "ToolBar": "thanh công cụ",
    "Window": "cửa sổ",
}

_MAX_NAME_LEN = 60

_lock = threading.Lock()
_desktop = None            # pywinauto Desktop, tạo lười (import pywinauto chậm)
_uia_disabled = False      # True khi đã thử và thất bại -> không thử lại
_tls = threading.local()   # UIA/COM cần CoInitialize theo từng luồng


def friendly_element_label(control_type: str, name: str) -> str:
    """Ghép loại control + tên thành nhãn tiếng Việt, vd "nút 'Đăng nhập'".

    Trả về chuỗi rỗng nếu không có tên (nhãn toạ độ vẫn dùng được).
    """
    name = " ".join((name or "").split())
    if not name:
        return ""
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN - 1] + "…"
    kind = CONTROL_NAMES_VI.get((control_type or "").strip())
    return f"{kind} '{name}'" if kind else f"'{name}'"


def _ensure_com_initialized():
    if getattr(_tls, "done", False):
        return
    _tls.done = True
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


def describe_element_at(x: int, y: int) -> str:
    """Nhãn phần tử UI tại (x, y), hoặc "" nếu không xác định được.

    Được gọi từ luồng listener của pynput — mọi lỗi đều nuốt về "" để
    không bao giờ chặn luồng ghi.
    """
    global _desktop, _uia_disabled
    if sys.platform != "win32" or _uia_disabled:
        return ""
    try:
        _ensure_com_initialized()
        with _lock:
            if _desktop is None:
                from pywinauto import Desktop
                _desktop = Desktop(backend="uia")
            el = _desktop.from_point(x, y)
        info = el.element_info
        return friendly_element_label(info.control_type, info.name)
    except ImportError:
        _uia_disabled = True
        log.info("Không có pywinauto — bỏ qua nhận diện phần tử UI. "
                 "Cài bằng: pip install pywinauto")
        return ""
    except Exception:
        log.debug("Không đọc được phần tử UI tại (%s, %s)", x, y, exc_info=True)
        return ""
