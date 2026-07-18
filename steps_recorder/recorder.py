"""Bộ máy ghi thao tác: hook chuột/bàn phím toàn cục, chụp màn hình, quản lý bước."""
import base64
import datetime as dt
import io
import json
import logging
import threading
import time
from typing import List, Optional

from PIL import Image, ImageDraw

from . import exporters
from .deps import _HAS_GW, _HAS_MSS, _PYNPUT_ERROR, ImageGrab, gw, keyboard, mouse, mss
from .element import describe_element_at
from .models import PROJECT_FORMAT, PROJECT_VERSION, Step

log = logging.getLogger("steps_recorder")

# Phím tắt toàn cục của ứng dụng — không được ghi vào các bước
HOTKEY_IGNORED_KEYS = (
    {keyboard.Key.f9, keyboard.Key.f10} if keyboard is not None else set())


MASKED_TEXT_ACTION = "Nhập văn bản (nội dung đã ẩn)"


def format_typed_action(text: str, masked: bool) -> str:
    """Nhãn cho bước gõ phím. masked=True: không lộ nội dung đã gõ."""
    if masked:
        return MASKED_TEXT_ACTION
    return f'Nhập văn bản: "{text}"'


def is_double_click(prev, now_t: float, x: int, y: int, button_name: str,
                    max_dt: float = 0.4, max_dist: int = 8) -> bool:
    """prev = (t, x, y, button_name) của click trước, hoặc None."""
    if not prev:
        return False
    t0, x0, y0, btn0 = prev
    return (btn0 == button_name
            and 0 <= now_t - t0 <= max_dt
            and max(abs(x - x0), abs(y - y0)) <= max_dist)


def pick_monitor(monitors: list, x: int, y: int) -> dict:
    """Chọn màn hình chứa điểm (x, y) theo định dạng mss.

    monitors: [0] là khung bao ảo toàn bộ, [1..] là từng màn hình thật.
    Toạ độ âm (màn hình bên trái/phía trên màn chính) vẫn đúng nhờ phép so
    sánh khoảng chứa. Không tìm thấy thì trả về màn hình chính.
    """
    for mon in monitors[1:]:
        if (mon["left"] <= x < mon["left"] + mon["width"]
                and mon["top"] <= y < mon["top"] + mon["height"]):
            return mon
    return monitors[1] if len(monitors) > 1 else monitors[0]


class StepsRecorder:
    HIGHLIGHT_RADIUS = 28       # bán kính vòng khoanh vị trí click (px)
    HIGHLIGHT_WIDTH = 5         # độ dày viền vòng khoanh
    HIGHLIGHT_COLOR = (255, 60, 60)  # đỏ

    def __init__(self):
        self.steps: List[Step] = []
        self.report_title = "Bản ghi các bước"
        self.report_summary = ""
        self.project_path: Optional[str] = None  # file .steps.json đang làm việc
        self._recording = False
        self._paused = False
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kbd_listener: Optional[keyboard.Listener] = None
        self._lock = threading.Lock()

        # Bộ đệm gom phím gõ thành một bước văn bản
        self._key_buffer: List[str] = []
        self._key_buffer_window = ""
        self._last_key_time = 0.0
        self.on_step_added = None   # callback(step) để cập nhật giao diện
        self.on_error = None        # callback(msg) báo lỗi không chặn luồng ghi

        # Che nội dung gõ phím (mật khẩu, dữ liệu nhạy cảm) — xem _flush_keys
        self.mask_typed_text = True

        # Nhận diện phần tử UI được click (Windows + pywinauto; nơi khác no-op)
        self.capture_ui_elements = True

        # Nhận diện nhấp đúp: (t, x, y, button_str, step) của click gần nhất
        self._last_click = None

    # ---- Trạng thái ----
    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def step_count(self) -> int:
        return len(self.steps)

    # ---- Điều khiển ----
    def start(self):
        if self._recording:
            return
        if mouse is None or keyboard is None:
            raise RuntimeError(
                f"Không dùng được pynput để ghi thao tác: {_PYNPUT_ERROR}")
        self.steps.clear()
        self.report_title = "Bản ghi các bước"
        self.report_summary = ""
        self.project_path = None
        self._last_click = None
        self._recording = True
        self._paused = False
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._kbd_listener = keyboard.Listener(on_press=self._on_key)
        self._mouse_listener.start()
        self._kbd_listener.start()

    def pause(self):
        if self._recording:
            self._flush_keys()
            self._paused = not self._paused

    def stop(self):
        if not self._recording:
            return
        self._flush_keys()
        self._recording = False
        self._paused = False
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._kbd_listener:
            self._kbd_listener.stop()
            self._kbd_listener = None

    def clear_session(self):
        """Xoá phiên hiện tại (dừng ghi nếu đang ghi, reset bước/tiêu đề/dự án)."""
        if self._recording:
            self.stop()
        self.steps.clear()
        self.report_title = "Bản ghi các bước"
        self.report_summary = ""
        self.project_path = None
        self._key_buffer.clear()
        self._key_buffer_window = ""
        self._last_key_time = 0.0
        self._last_click = None

    # ---- Chỉnh sửa danh sách bước ----
    def delete_step(self, i: int):
        with self._lock:
            if 0 <= i < len(self.steps):
                self.steps.pop(i)
                self._renumber()

    def _renumber(self):
        for idx, s in enumerate(self.steps, start=1):
            s.index = idx

    def update_step(self, i: int, label: Optional[str] = None,
                    description: Optional[str] = None,
                    section: Optional[str] = None):
        with self._lock:
            if 0 <= i < len(self.steps):
                if label is not None:
                    self.steps[i].action = label
                if description is not None:
                    self.steps[i].description = description
                if section is not None:
                    self.steps[i].section = section

    # ---- Tiện ích ----
    @staticmethod
    def _now() -> str:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _active_window_title() -> str:
        if _HAS_GW:
            try:
                w = gw.getActiveWindow()
                if w and w.title:
                    return w.title
            except Exception:
                pass
        return "(không xác định)"

    def _grab_screen(self, x: Optional[int] = None,
                     y: Optional[int] = None) -> Image.Image:
        if _HAS_MSS:
            with mss.mss() as sct:
                if x is not None and y is not None:
                    mon = pick_monitor(sct.monitors, int(x), int(y))
                else:
                    mon = sct.monitors[1]  # màn hình chính
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                self._origin = (mon["left"], mon["top"])
                return img
        else:
            img = ImageGrab.grab()
            self._origin = (0, 0)
            return img.convert("RGB")

    def _mark(self, img: Image.Image, x: int, y: int) -> Image.Image:
        """Khoanh tròn kép quanh vị trí click cho dễ thấy."""
        ox, oy = getattr(self, "_origin", (0, 0))
        cx, cy = x - ox, y - oy
        draw = ImageDraw.Draw(img)
        for r, w in ((self.HIGHLIGHT_RADIUS, self.HIGHLIGHT_WIDTH),
                     (self.HIGHLIGHT_RADIUS + 8, 2)):
            draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                         outline=self.HIGHLIGHT_COLOR, width=w)
        return img

    @staticmethod
    def _to_b64(img: Image.Image, max_width: int = 1280) -> str:
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _add_step(self, action: str, image_b64: Optional[str], window: str,
                  description: str = ""):
        with self._lock:
            step = Step(
                index=len(self.steps) + 1,
                timestamp=self._now(),
                action=action,
                window=window,
                description=description,
                images=[image_b64] if image_b64 else [],
            )
            self.steps.append(step)
        if self.on_step_added:
            try:
                self.on_step_added(step)
            except Exception:
                log.exception("Lỗi callback on_step_added")
        return step

    # ---- Xử lý sự kiện chuột ----
    def _on_click(self, x, y, button, pressed):
        if not self._recording or self._paused or not pressed:
            return
        self._flush_keys()  # đóng bước văn bản trước một cú click
        btn = {"Button.left": "trái", "Button.right": "phải",
               "Button.middle": "giữa"}.get(str(button), str(button))

        # Tên phần tử UI được click, vd "vào nút 'Đăng nhập' " (Windows)
        elem = describe_element_at(x, y) if self.capture_ui_elements else ""
        target = f"vào {elem} " if elem else ""

        # Nhấp đúp: nâng cấp bước click liền trước thay vì thêm bước mới.
        # Điều kiện steps[-1] is prev_step bảo đảm không có bước nào chen giữa
        # (vd _flush_keys ở trên vừa thêm một bước văn bản).
        now = time.time()
        prev = self._last_click
        if (prev is not None
                and is_double_click(prev[:4], now, x, y, str(button))):
            with self._lock:
                if self.steps and self.steps[-1] is prev[4]:
                    prev[4].action = f"Nhấp đúp chuột {btn} {target}tại ({x}, {y})"
                    self._last_click = None  # nhấp lần 3 tính là chuỗi mới
                    return

        window = self._active_window_title()
        try:
            img = self._grab_screen(x, y)
            img = self._mark(img, x, y)
            b64 = self._to_b64(img)
        except Exception as e:
            b64 = None
            window += f"  [lỗi chụp màn hình: {e}]"
            log.exception("Lỗi chụp màn hình tại (%s, %s)", x, y)
            if self.on_error:
                try:
                    self.on_error("Lỗi chụp màn hình (bước vẫn được ghi)")
                except Exception:
                    pass
        action = f"Nhấp chuột {btn} {target}tại ({x}, {y})"
        step = self._add_step(action, b64, window)
        self._last_click = (now, x, y, str(button), step)

    # ---- Xử lý sự kiện bàn phím ----
    def _on_key(self, key):
        if key in HOTKEY_IGNORED_KEYS:
            return  # F9/F10 điều khiển ứng dụng, không phải thao tác cần ghi
        if not self._recording or self._paused:
            return
        now = time.time()
        # Nếu ngắt quãng quá 2 giây thì chốt bước cũ
        if self._key_buffer and now - self._last_key_time > 2.0:
            self._flush_keys()
        self._last_key_time = now
        try:
            ch = key.char
        except AttributeError:
            ch = None
        if ch is not None:
            # key.char có thể là None (Ctrl+phím, phím đặc biệt vẫn có .char)
            self._key_buffer.append(ch if isinstance(ch, str) else str(ch))
        else:
            name = str(key).replace("Key.", "")
            if name == "space":
                self._key_buffer.append(" ")
            elif name == "enter":
                self._key_buffer.append("↵")
                self._flush_keys()
            else:
                # phím đặc biệt -> chốt bộ đệm rồi ghi riêng một bước
                self._flush_keys()
                if not self._key_buffer_window:
                    self._key_buffer_window = self._active_window_title()
                self._add_step(f"Nhấn phím [{name}]", None, self._key_buffer_window)
                self._key_buffer_window = ""

        if not self._key_buffer_window:
            self._key_buffer_window = self._active_window_title()

    def _flush_keys(self):
        if self._key_buffer:
            text = "".join(c for c in self._key_buffer if isinstance(c, str))
            if text:
                # mask_typed_text: nội dung gốc bị loại bỏ ngay tại đây, không
                # bao giờ đi vào Step / file dự án / HTML / tin nhắn gửi AI.
                self._add_step(format_typed_action(text, self.mask_typed_text),
                               None,
                               self._key_buffer_window or self._active_window_title())
            self._key_buffer.clear()
            self._key_buffer_window = ""

    # ---- Lưu / mở dự án (tiếp tục làm sau) ----
    def to_project_dict(self) -> dict:
        return {
            "format": PROJECT_FORMAT,
            "version": PROJECT_VERSION,
            "saved_at": self._now(),
            "title": self.report_title,
            "summary": self.report_summary,
            "steps": [s.to_dict() for s in self.steps],
        }

    def save_project(self, path: str) -> str:
        if not path.lower().endswith((".json", ".steps.json")):
            path = path + ".steps.json"
        data = self.to_project_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.project_path = path
        return path

    def load_project(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("File dự án không hợp lệ.")
        fmt = data.get("format")
        if fmt and fmt != PROJECT_FORMAT:
            raise ValueError(f"Định dạng không hỗ trợ: {fmt}")
        steps_raw = data.get("steps")
        if steps_raw is None and isinstance(data.get("data"), dict):
            # dự phòng cấu trúc lồng
            steps_raw = data["data"].get("steps")
        if not isinstance(steps_raw, list):
            raise ValueError("File không chứa danh sách steps.")
        loaded: List[Step] = []
        for item in steps_raw:
            if isinstance(item, dict):
                loaded.append(Step.from_dict(item))
        if not loaded:
            raise ValueError("Dự án không có bước nào.")
        self.steps = loaded
        self._renumber()
        self.report_title = str(data.get("title") or "Bản ghi các bước")
        self.report_summary = str(data.get("summary") or "")
        self.project_path = path


    # ---- Xuất báo cáo (uỷ quyền cho exporters) ----
    def export_html(self, path: str, title: Optional[str] = None,
                    include_toc: bool = True) -> str:
        return exporters.export_html(self, path, title=title,
                                     include_toc=include_toc)

    def export_markdown(self, path: str, title: Optional[str] = None) -> str:
        return exporters.export_markdown(self, path, title=title)

    def export_docx(self, path: str, title: Optional[str] = None) -> str:
        return exporters.export_docx(self, path, title=title)
