"""Tiện ích riêng cho Windows."""
import logging
import sys

log = logging.getLogger("steps_recorder")


def enable_dpi_awareness() -> None:
    """Bật DPI awareness trên Windows.

    Khi màn hình scale 125%/150%, toạ độ pynput (pixel vật lý) và ảnh mss có
    thể lệch nhau nếu tiến trình không DPI-aware — vòng khoanh đỏ sẽ sai chỗ.
    Phải gọi TRƯỚC khi tạo cửa sổ Tk hay chụp màn hình. Trên hệ khác là no-op.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # 2 = PER_MONITOR_DPI_AWARE (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        log.warning("Không bật được DPI awareness", exc_info=True)
