"""Import thư viện bên thứ ba với guard an toàn cho môi trường headless.

pynput có thể lỗi cả khi ĐÃ cài (vd không có X display trên Linux headless),
nên bắt Exception rộng và chỉ dừng hẳn khi chạy như ứng dụng (__main__).
"""
from typing import Optional

try:
    from pynput import mouse, keyboard
    _PYNPUT_ERROR: Optional[Exception] = None
except Exception as _e:
    mouse = keyboard = None  # type: ignore[assignment]
    _PYNPUT_ERROR = _e

try:
    from PIL import ImageTk  # hiển thị thumbnail trong cửa sổ chỉnh sửa
    _HAS_IMAGETK = True
except Exception:
    ImageTk = None  # type: ignore[assignment]
    _HAS_IMAGETK = False

try:
    import mss  # chụp màn hình nhanh, đa nền tảng
    _HAS_MSS = True
except ImportError:
    mss = None  # type: ignore[assignment]
    _HAS_MSS = False

try:
    from PIL import ImageGrab  # dự phòng khi thiếu mss (Windows/macOS)
except Exception:
    ImageGrab = None  # type: ignore[assignment]

try:
    import pygetwindow as gw  # lấy tiêu đề cửa sổ active
    _HAS_GW = True
except Exception:
    # Trên Linux, import pygetwindow ném NotImplementedError (không phải
    # ImportError) — coi như không có, tính năng chỉ là tuỳ chọn.
    gw = None  # type: ignore[assignment]
    _HAS_GW = False
