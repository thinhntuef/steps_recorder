"""Điểm khởi chạy ứng dụng: python -m steps_recorder (hoặc python main.py)."""
import logging

from .deps import _PYNPUT_ERROR
from .winutil import enable_dpi_awareness


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    if _PYNPUT_ERROR is not None:
        raise SystemExit(
            "Thiếu hoặc không dùng được 'pynput'. Cài bằng: pip install pynput\n"
            f"(Chi tiết: {_PYNPUT_ERROR})")
    enable_dpi_awareness()  # phải gọi trước khi tạo Tk / chụp màn hình
    from .gui.main_window import RecorderGUI
    RecorderGUI().run()


if __name__ == "__main__":
    main()
