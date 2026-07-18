"""Cửa sổ điều khiển chính (Ghi / Tạm dừng / Dừng, phím tắt, cấu hình)."""
import datetime as dt
import logging
import tkinter as tk
from tkinter import filedialog, messagebox

from ..config import CONFIG_FILETYPES, CONFIG_PATH, AppConfig
from ..deps import keyboard
from ..models import PROJECT_FILETYPES, Step
from ..recorder import StepsRecorder
from .review import ReviewWindow
from .settings import SettingsDialog
from .theme import UITheme, _apply_ttk_theme, _btn, _ui_font

log = logging.getLogger("steps_recorder")


class RecorderGUI:
    def __init__(self):
        self.config = AppConfig.load()
        self.rec = StepsRecorder()
        self.rec.on_step_added = self._on_step_added

        self.root = tk.Tk()
        self.root.title("Steps Recorder")
        self.root.geometry("420x440")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=UITheme.BG)
        _apply_ttk_theme(self.root)
        self._review = None

        self.status = tk.StringVar(value="Sẵn sàng")
        self.count = tk.StringVar(value="0")
        self._state_key = "idle"  # idle | recording | paused | stopped

        # Header
        header = tk.Frame(self.root, bg=UITheme.BRAND)
        header.pack(fill="x")
        tk.Label(header, text="Steps Recorder", bg=UITheme.BRAND, fg="#ffffff",
                 font=_ui_font(15, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(header, text="Ghi lại thao tác · Biên soạn hướng dẫn · Xuất HTML",
                 bg=UITheme.BRAND, fg="#cfe2f7",
                 font=_ui_font(UITheme.FONT_SMALL)).pack(anchor="w", padx=18, pady=(0, 14))

        body = tk.Frame(self.root, bg=UITheme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)

        # Status card
        status_card = tk.Frame(body, bg=UITheme.SURFACE, highlightthickness=1,
                               highlightbackground=UITheme.BORDER)
        status_card.pack(fill="x", pady=(0, 14))

        self._dot = tk.Label(status_card, text="●", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                             font=_ui_font(14))
        self._dot.pack(side="left", padx=(16, 8), pady=16)

        mid = tk.Frame(status_card, bg=UITheme.SURFACE)
        mid.pack(side="left", fill="x", expand=True, pady=12)
        self._status_lbl = tk.Label(mid, textvariable=self.status, bg=UITheme.SURFACE,
                                    fg=UITheme.TEXT, font=_ui_font(12, "bold"),
                                    anchor="w")
        self._status_lbl.pack(fill="x")
        tk.Label(mid, text="Trạng thái ghi", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL), anchor="w").pack(fill="x")

        count_box = tk.Frame(status_card, bg=UITheme.BRAND_SOFT)
        count_box.pack(side="right", padx=12, pady=10)
        tk.Label(count_box, textvariable=self.count, bg=UITheme.BRAND_SOFT,
                 fg=UITheme.BRAND, font=_ui_font(18, "bold")).pack(padx=14, pady=(8, 0))
        tk.Label(count_box, text="bước", bg=UITheme.BRAND_SOFT, fg=UITheme.BRAND,
                 font=_ui_font(UITheme.FONT_SMALL)).pack(padx=14, pady=(0, 8))

        # Control buttons
        bar = tk.Frame(body, bg=UITheme.BG)
        bar.pack(fill="x", pady=(0, 10))
        bar.columnconfigure((0, 1, 2), weight=1)

        self.btn_start = _btn(bar, "●  Ghi", command=self.start, variant="record")
        self.btn_pause = _btn(bar, "⏸  Tạm dừng", command=self.pause, variant="secondary",
                              state="disabled")
        self.btn_stop = _btn(bar, "■  Dừng & Sửa", command=self.stop, variant="primary",
                             state="disabled")
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_stop.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # Secondary actions
        bar2 = tk.Frame(body, bg=UITheme.BG)
        bar2.pack(fill="x", pady=(0, 6))
        bar2.columnconfigure((0, 1), weight=1)
        _btn(bar2, "🆕  Ghi phiên mới", command=self.new_session,
             variant="secondary").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _btn(bar2, "📂  Mở dự án", command=self.open_project,
             variant="ghost").grid(row=0, column=1, sticky="ew", padx=(4, 0))

        bar3 = tk.Frame(body, bg=UITheme.BG)
        bar3.pack(fill="x")
        bar3.columnconfigure((0, 1, 2), weight=1)
        _btn(bar3, "⚙  Cấu hình", command=self.open_settings,
             variant="ghost").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _btn(bar3, "⬆ Xuất cấu hình", command=self.export_config,
             variant="ghost").grid(row=0, column=1, sticky="ew", padx=4)
        _btn(bar3, "⬇ Nhập cấu hình", command=self.import_config,
             variant="ghost").grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self.var_mask = tk.BooleanVar(value=bool(self.config.mask_typed_text))
        tk.Checkbutton(
            body, text="🔒 Ẩn nội dung gõ phím (mật khẩu, dữ liệu nhạy cảm)",
            variable=self.var_mask, command=self._toggle_mask,
            bg=UITheme.BG, fg=UITheme.TEXT, activebackground=UITheme.BG,
            selectcolor=UITheme.SURFACE, font=_ui_font(UITheme.FONT_SMALL),
            anchor="w",
        ).pack(fill="x", pady=(10, 0))

        tip = tk.Label(
            body,
            text="Phím tắt: F9 Ghi / Tạm dừng · F10 Dừng & sửa. "
                 "Cửa sổ luôn nổi trên cùng khi ghi.",
            bg=UITheme.BG, fg=UITheme.MUTED, font=_ui_font(UITheme.FONT_SMALL),
            wraplength=380, justify="left",
        )
        tip.pack(fill="x", pady=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.rec.on_error = self._on_rec_error

        # Phím tắt toàn cục (không khả dụng trên Wayland -> bỏ qua nếu lỗi)
        self._hotkeys = None
        if keyboard is not None:
            try:
                self._hotkeys = keyboard.GlobalHotKeys({
                    "<f9>": self._hk_toggle,
                    "<f10>": self._hk_stop,
                })
                self._hotkeys.start()
            except Exception:
                self._hotkeys = None
                log.warning("Không đăng ký được phím tắt toàn cục F9/F10",
                            exc_info=True)

    def _set_status_visual(self, key: str):
        """Cập nhật màu chấm trạng thái theo trạng thái ghi."""
        self._state_key = key
        colors = {
            "idle": UITheme.MUTED,
            "recording": UITheme.RECORD,
            "paused": UITheme.WARNING,
            "stopped": UITheme.SUCCESS,
            "loaded": UITheme.BRAND,
        }
        self._dot.configure(fg=colors.get(key, UITheme.MUTED))

    def _toggle_mask(self):
        self.config.mask_typed_text = bool(self.var_mask.get())
        self.rec.mask_typed_text = self.config.mask_typed_text
        self.config.save()

    def open_settings(self):
        SettingsDialog(self.root, self.config)

    def export_config(self):
        default = f"steps_recorder_{dt.datetime.now():%Y%m%d_%H%M%S}.config.json"
        path = filedialog.asksaveasfilename(
            defaultextension=".config.json", initialfile=default,
            filetypes=CONFIG_FILETYPES, parent=self.root)
        if not path:
            return
        include_key = False
        if (self.config.api_key or "").strip():
            include_key = messagebox.askyesno(
                "Cấu hình",
                "Mặc định KHÔNG xuất API key (an toàn khi chia sẻ).\n\n"
                "Bạn có muốn GỒM API key trong file không?\n"
                "(Chỉ chọn Có nếu file chỉ dùng riêng, không gửi cho người khác.)")
        try:
            saved = self.config.export_to(path, include_api_key=include_key)
            note = " (có API key)" if include_key else " (đã ẩn API key)"
            messagebox.showinfo("Cấu hình", f"Đã xuất cấu hình{note}:\n{saved}")
        except Exception as e:
            messagebox.showerror("Cấu hình", f"Xuất cấu hình thất bại:\n{e}")

    def import_config(self):
        path = filedialog.askopenfilename(
            filetypes=CONFIG_FILETYPES, parent=self.root)
        if not path:
            return
        try:
            self.config.import_from(path)
            if not self.config.save():
                messagebox.showwarning(
                    "Cấu hình",
                    "Đã nhập cấu hình nhưng KHÔNG lưu được file:\n"
                    f"{CONFIG_PATH}\n\nCấu hình chỉ áp dụng cho phiên này.")
            else:
                messagebox.showinfo(
                    "Cấu hình",
                    f"Đã nhập và lưu cấu hình:\n{path}")
        except Exception as e:
            messagebox.showerror("Cấu hình", f"Nhập cấu hình thất bại:\n{e}")

    def new_session(self):
        if self.rec.is_recording:
            if not messagebox.askyesno(
                    "Ghi phiên mới",
                    "Đang ghi. Dừng và xoá phiên hiện tại?"):
                return
        elif self.rec.step_count > 0:
            if not messagebox.askyesno(
                    "Ghi phiên mới",
                    f"Phiên hiện có {self.rec.step_count} bước.\n"
                    "Xoá hết và bắt đầu phiên mới?"):
                return
        self.rec.clear_session()
        self._close_review()
        self.status.set("Sẵn sàng")
        self.count.set("0")
        self._set_status_visual("idle")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  Tạm dừng")
        self.btn_stop.config(state="disabled")

    def _close_review(self):
        if self._review is None:
            return
        try:
            if self._review.winfo_exists():
                self._review._close()
        except Exception:
            pass
        self._review = None

    def open_project(self):
        if self.rec.is_recording:
            messagebox.showwarning(
                "Steps Recorder", "Hãy dừng ghi trước khi mở dự án.")
            return
        path = filedialog.askopenfilename(
            filetypes=PROJECT_FILETYPES, parent=self.root)
        if not path:
            return
        try:
            self.rec.load_project(path)
        except Exception as e:
            messagebox.showerror("Steps Recorder", f"Mở dự án thất bại:\n{e}")
            return
        self.status.set("Đã mở dự án")
        self.count.set(str(self.rec.step_count))
        self._set_status_visual("loaded")
        self._open_review()

    def start(self):
        if self.rec.step_count > 0 and not self.rec.is_recording:
            if not messagebox.askyesno(
                    "Ghi",
                    f"Bắt đầu ghi sẽ xoá {self.rec.step_count} bước hiện có.\n"
                    "Tiếp tục?"):
                return
        self._close_review()
        self.rec.mask_typed_text = bool(self.config.mask_typed_text)
        self.rec.start()
        self.status.set("Đang ghi…")
        self.count.set("0")
        self._set_status_visual("recording")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")

    def pause(self):
        self.rec.pause()
        if self.rec.is_paused:
            self.status.set("Đã tạm dừng")
            self._set_status_visual("paused")
            self.btn_pause.config(text="▶  Tiếp tục")
        else:
            self.status.set("Đang ghi…")
            self._set_status_visual("recording")
            self.btn_pause.config(text="⏸  Tạm dừng")

    def stop(self):
        self.rec.stop()
        self.status.set("Đã dừng")
        self._set_status_visual("stopped")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  Tạm dừng")
        self.btn_stop.config(state="disabled")

        if self.rec.step_count == 0:
            messagebox.showinfo("Steps Recorder", "Chưa ghi được bước nào.")
            return
        self._open_review()

    def _open_review(self):
        if self._review is not None:
            try:
                if self._review.winfo_exists():
                    # Đồng bộ lại nội dung (vd sau khi Mở dự án)
                    self._review.var_title.set(self.rec.report_title)
                    self._review.txt_summary.delete("1.0", "end")
                    self._review.txt_summary.insert("1.0", self.rec.report_summary)
                    self._review._backup = None
                    self._review.btn_undo.config(state="disabled")
                    self._review._render_steps()
                    self._review._refresh_title_bar()
                    self._review.status.set(
                        f"{self.rec.step_count} bước · đã mở dự án")
                    self._review.lift()
                    self._review.focus_force()
                    return
            except Exception:
                pass
        win = ReviewWindow(self.root, self.rec, self.config,
                           on_settings=self.open_settings)
        self._review = win
        if self.rec.project_path:
            win._refresh_title_bar()

    def _on_step_added(self, step: Step):
        # Chạy từ luồng listener của pynput -> chuyển về luồng Tk
        self.root.after(0, lambda: self.count.set(str(step.index)))

    def _on_rec_error(self, msg: str):
        self.root.after(0, lambda: self.status.set(msg))

    # ---- phím tắt toàn cục (chạy trong luồng pynput -> chuyển về luồng Tk) --
    def _hk_toggle(self):
        self.root.after(0, self._do_hk_toggle)

    def _do_hk_toggle(self):
        if self.rec.is_recording:
            self.pause()
        else:
            self.start()

    def _hk_stop(self):
        self.root.after(0, self._do_hk_stop)

    def _do_hk_stop(self):
        if self.rec.is_recording:
            self.stop()

    def _on_close(self):
        if self.rec.is_recording:
            self.rec.stop()
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

