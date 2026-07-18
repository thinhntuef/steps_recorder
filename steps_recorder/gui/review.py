"""Cửa sổ Xem lại & Chỉnh sửa các bước sau khi ghi."""
import base64
import copy
import io
import datetime as dt
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from ..ai import apply_ai_result, call_ai, call_ai_html
from ..config import AppConfig
from ..deps import _HAS_IMAGETK, ImageTk
from ..models import PROJECT_FILETYPES
from ..recorder import StepsRecorder
from .theme import (UITheme, _apply_ttk_theme, _btn, _section_card,
                    _style_entry, _style_text, _ui_font)
from .viewer import ImageViewer


class ReviewWindow(tk.Toplevel):
    def __init__(self, parent, recorder: StepsRecorder, config: AppConfig, on_settings):
        super().__init__(parent)
        self.title("Xem lại & chỉnh sửa các bước")
        self.rec = recorder
        self.config_obj = config
        self.on_settings = on_settings
        self.geometry("960x720")
        self.minsize(820, 560)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._backup = None   # snapshot trước lần AI gần nhất
        self.configure(bg=UITheme.BG)
        _apply_ttk_theme(self)

        # Header
        header = tk.Frame(self, bg=UITheme.BRAND)
        header.pack(fill="x")
        left_h = tk.Frame(header, bg=UITheme.BRAND)
        left_h.pack(side="left", fill="x", expand=True, padx=18, pady=14)
        tk.Label(left_h, text="Xem lại & chỉnh sửa", bg=UITheme.BRAND, fg="#ffffff",
                 font=_ui_font(14, "bold")).pack(anchor="w")
        self.status = tk.StringVar(value=f"{recorder.step_count} bước")
        tk.Label(left_h, textvariable=self.status, bg=UITheme.BRAND, fg="#cfe2f7",
                 font=_ui_font(UITheme.FONT_SMALL)).pack(anchor="w", pady=(2, 0))

        # Meta: tiêu đề + tóm tắt
        meta_outer, meta = _section_card(self)
        meta_outer.pack(fill="x", padx=14, pady=(12, 0))
        meta.columnconfigure(1, weight=1)

        tk.Label(meta, text="TIÊU ĐỀ", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(row=0, column=0, sticky="w")
        self.var_title = tk.StringVar(value=recorder.report_title)
        _style_entry(tk.Entry(meta, textvariable=self.var_title)).grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 8))

        tk.Label(meta, text="TÓM TẮT", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(
            row=1, column=0, sticky="nw", pady=(4, 0))
        self.txt_summary = _style_text(tk.Text(meta, height=3))
        self.txt_summary.insert("1.0", recorder.report_summary)
        self.txt_summary.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

        # Thanh công cụ
        bar = tk.Frame(self, bg=UITheme.BG)
        bar.pack(fill="x", padx=14, pady=(10, 6))

        left_bar = tk.Frame(bar, bg=UITheme.BG)
        left_bar.pack(side="left")
        self.var_toc = tk.BooleanVar(value=config.export_toc)
        tk.Checkbutton(
            left_bar, text="Menu trái (mục lục HTML)", variable=self.var_toc,
            bg=UITheme.BG, fg=UITheme.TEXT, activebackground=UITheme.BG,
            selectcolor=UITheme.SURFACE, font=_ui_font(UITheme.FONT_SMALL),
        ).pack(side="left")

        right_bar = tk.Frame(bar, bg=UITheme.BG)
        right_bar.pack(side="right")
        _btn(right_bar, "📂 Mở", command=self._open_project, variant="ghost").pack(
            side="left", padx=2)
        _btn(right_bar, "💾 Dự án", command=self._save_project, variant="secondary").pack(
            side="left", padx=2)
        _btn(right_bar, "💾 HTML", command=self._export, variant="primary").pack(
            side="left", padx=2)
        _btn(right_bar, "📝 Markdown", command=self._export_md,
             variant="secondary").pack(side="left", padx=2)
        _btn(right_bar, "📄 DOCX", command=self._export_docx,
             variant="secondary").pack(side="left", padx=2)
        _btn(right_bar, "⚙ Cấu hình", command=self.on_settings, variant="ghost").pack(
            side="left", padx=2)
        self.btn_undo = _btn(right_bar, "↩ Hoàn tác AI", command=self._undo_ai,
                             variant="ghost", state="disabled")
        self.btn_undo.pack(side="left", padx=2)
        self.btn_ai = _btn(right_bar, "✨ AI biên soạn HDSD", command=self._run_ai,
                           variant="accent")
        self.btn_ai.pack(side="left", padx=(6, 0))
        self.btn_ai_html = _btn(right_bar, "🎨 AI tạo HTML", command=self._run_ai_html,
                                variant="accent")
        self.btn_ai_html.pack(side="left", padx=(6, 0))

        # Danh sách bước (cuộn được)
        list_wrap = tk.Frame(self, bg=UITheme.BG)
        list_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        list_card = tk.Frame(list_wrap, bg=UITheme.SURFACE, highlightthickness=1,
                             highlightbackground=UITheme.BORDER)
        list_card.pack(fill="both", expand=True)

        list_head = tk.Frame(list_card, bg=UITheme.SURFACE)
        list_head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(list_head, text="Các bước đã ghi", bg=UITheme.SURFACE, fg=UITheme.BRAND,
                 font=_ui_font(UITheme.FONT_HEAD, "bold")).pack(side="left")

        container = tk.Frame(list_card, bg=UITheme.SURFACE)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(container, highlightthickness=0, bg=UITheme.SURFACE_2,
                                bd=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=UITheme.SURFACE_2)
        self._win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        self._row_widgets = []  # [(section_var, label_var, desc_text), ...]
        self._render_steps()

    # ---- cuộn chuột ----
    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _close(self):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.destroy()

    # ---- dựng danh sách ----
    def _make_thumb(self, b64):
        if not (b64 and _HAS_IMAGETK):
            return None
        try:
            img = Image.open(io.BytesIO(base64.b64decode(b64)))
            img.thumbnail((150, 110))
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _open_image(self, b64, title: str = "Xem ảnh"):
        if not b64:
            return
        ImageViewer(self, b64, title=title)

    def _render_steps(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self._row_widgets = []
        if not self.rec.steps:
            empty = tk.Frame(self.list_frame, bg=UITheme.SURFACE_2)
            empty.pack(fill="x", pady=40)
            tk.Label(empty, text="Chưa có bước nào", bg=UITheme.SURFACE_2,
                     fg=UITheme.MUTED, font=_ui_font(11)).pack()
            self.status.set("0 bước")
            return

        for i, s in enumerate(self.rec.steps):
            card = tk.Frame(self.list_frame, bg=UITheme.SURFACE, highlightthickness=1,
                            highlightbackground=UITheme.BORDER)
            card.pack(fill="x", expand=True, pady=6, padx=6)

            # accent strip + head
            head = tk.Frame(card, bg=UITheme.SURFACE)
            head.pack(fill="x", padx=12, pady=(10, 4))
            badge = tk.Label(
                head, text=f"Bước {s.index}", bg=UITheme.BRAND_SOFT, fg=UITheme.BRAND,
                font=_ui_font(UITheme.FONT_SMALL, "bold"), padx=10, pady=3)
            badge.pack(side="left")
            tk.Label(head, text=s.timestamp, bg=UITheme.SURFACE, fg=UITheme.MUTED,
                     font=_ui_font(UITheme.FONT_SMALL)).pack(side="left", padx=12)
            _btn(head, "🗑 Xóa", command=lambda idx=i: self._delete(idx),
                 variant="danger").pack(side="right")

            body = tk.Frame(card, bg=UITheme.SURFACE)
            body.pack(fill="x", padx=12, pady=(0, 6))
            body.columnconfigure(1, weight=1)

            def field_label(r, text):
                tk.Label(body, text=text, bg=UITheme.SURFACE, fg=UITheme.MUTED,
                         font=_ui_font(UITheme.FONT_SMALL, "bold"), width=7,
                         anchor="w").grid(row=r, column=0, sticky="nw", pady=3)

            field_label(0, "PHẦN")
            sv = tk.StringVar(value=s.section or "")
            _style_entry(tk.Entry(body, textvariable=sv)).grid(
                row=0, column=1, sticky="ew", pady=3, padx=(4, 0))

            field_label(1, "NHÃN")
            lv = tk.StringVar(value=s.action)
            _style_entry(tk.Entry(body, textvariable=lv)).grid(
                row=1, column=1, sticky="ew", pady=3, padx=(4, 0))

            field_label(2, "MÔ TẢ")
            dtext = _style_text(tk.Text(body, height=3))
            dtext.insert("1.0", s.description)
            dtext.grid(row=2, column=1, sticky="ew", pady=3, padx=(4, 0))

            if s.window:
                win_row = tk.Frame(body, bg=UITheme.SURFACE_2)
                win_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 2))
                tk.Label(win_row, text="🪟  " + s.window, bg=UITheme.SURFACE_2,
                         fg=UITheme.MUTED, font=_ui_font(UITheme.FONT_SMALL),
                         wraplength=780, justify="left", anchor="w",
                         padx=8, pady=5).pack(fill="x")

            if s.images:
                strip = tk.Frame(card, bg=UITheme.SURFACE)
                strip.pack(fill="x", padx=12, pady=(2, 12))
                tk.Label(strip, text=f"Ảnh ({len(s.images)}) — nhấp để phóng to",
                         bg=UITheme.SURFACE, fg=UITheme.MUTED,
                         font=_ui_font(UITheme.FONT_SMALL, "bold")).pack(
                    side="left", padx=(0, 8), anchor="n")
                for j, b in enumerate(s.images):
                    cell = tk.Frame(strip, bg=UITheme.SURFACE_2, highlightthickness=1,
                                    highlightbackground=UITheme.BORDER)
                    cell.pack(side="left", padx=(0, 8), pady=2)
                    thumb = self._make_thumb(b)
                    open_cmd = lambda b64=b, idx=s.index, sj=j: self._open_image(
                        b64, f"Bước {idx} · ảnh {sj + 1}")
                    if thumb is not None:
                        lbl = tk.Label(cell, image=thumb, bg=UITheme.SURFACE_2,
                                       cursor="hand2")
                        lbl.image = thumb
                        lbl.pack(padx=4, pady=4)
                        lbl.bind("<Button-1>", lambda e, c=open_cmd: c())
                    else:
                        lbl = tk.Label(cell, text="(nhấp xem ảnh)", bg=UITheme.SURFACE_2,
                                       fg=UITheme.BRAND, width=14, cursor="hand2")
                        lbl.pack(padx=4, pady=4)
                        lbl.bind("<Button-1>", lambda e, c=open_cmd: c())
                    _btn(cell, "🔍 Phóng to", command=open_cmd,
                         variant="ghost").pack(fill="x", padx=4, pady=(0, 2))
                    _btn(cell, "✕ Xóa ảnh",
                         command=lambda si=i, sj=j: self._remove_image(si, sj),
                         variant="danger").pack(fill="x", padx=4, pady=(0, 4))

            self._row_widgets.append((sv, lv, dtext))
        self.status.set(f"{self.rec.step_count} bước")

    # ---- đọc widget -> Step ----
    def _sync_to_steps(self):
        self.rec.report_title = self.var_title.get().strip() or "Bản ghi các bước"
        self.rec.report_summary = self.txt_summary.get("1.0", "end").strip()
        for (sv, lv, dtext), s in zip(self._row_widgets, self.rec.steps):
            s.section = sv.get().strip()
            s.action = lv.get().strip() or s.action
            s.description = dtext.get("1.0", "end").strip()

    def _delete(self, idx):
        self._sync_to_steps()
        self.rec.delete_step(idx)
        self._render_steps()

    def _remove_image(self, step_i, img_j):
        self._sync_to_steps()
        if 0 <= step_i < len(self.rec.steps):
            imgs = self.rec.steps[step_i].images
            if 0 <= img_j < len(imgs):
                del imgs[img_j]
        self._render_steps()

    # ---- xuất HTML ----
    def _export(self):
        self._sync_to_steps()
        if self.rec.step_count == 0:
            messagebox.showinfo("Steps Recorder", "Không còn bước nào để lưu.", parent=self)
            return
        default = f"steps_{dt.datetime.now():%Y%m%d_%H%M%S}.html"
        path = filedialog.asksaveasfilename(
            defaultextension=".html", initialfile=default,
            filetypes=[("HTML", "*.html")], parent=self)
        if path:
            self.config_obj.export_toc = bool(self.var_toc.get())
            self.config_obj.save()
            self.rec.export_html(path, include_toc=self.config_obj.export_toc)
            messagebox.showinfo(
                "Steps Recorder",
                f"Đã xuất HTML ({self.rec.step_count} bước):\n{path}", parent=self)

    def _export_md(self):
        self._sync_to_steps()
        if self.rec.step_count == 0:
            messagebox.showinfo("Steps Recorder", "Không còn bước nào để lưu.", parent=self)
            return
        default = f"steps_{dt.datetime.now():%Y%m%d_%H%M%S}.md"
        path = filedialog.asksaveasfilename(
            defaultextension=".md", initialfile=default,
            filetypes=[("Markdown", "*.md")], parent=self)
        if not path:
            return
        try:
            saved = self.rec.export_markdown(path)
        except Exception as e:
            messagebox.showerror(
                "Steps Recorder", f"Xuất Markdown thất bại:\n{e}", parent=self)
            return
        messagebox.showinfo(
            "Steps Recorder",
            f"Đã xuất Markdown ({self.rec.step_count} bước):\n{saved}\n\n"
            "Lưu ý: ảnh nằm trong thư mục *_assets bên cạnh — khi chia sẻ hãy "
            "gửi kèm thư mục này.", parent=self)

    def _export_docx(self):
        self._sync_to_steps()
        if self.rec.step_count == 0:
            messagebox.showinfo("Steps Recorder", "Không còn bước nào để lưu.", parent=self)
            return
        default = f"steps_{dt.datetime.now():%Y%m%d_%H%M%S}.docx"
        path = filedialog.asksaveasfilename(
            defaultextension=".docx", initialfile=default,
            filetypes=[("Tài liệu Word", "*.docx")], parent=self)
        if not path:
            return
        try:
            saved = self.rec.export_docx(path)
        except Exception as e:
            messagebox.showerror(
                "Steps Recorder", f"Xuất DOCX thất bại:\n{e}", parent=self)
            return
        messagebox.showinfo(
            "Steps Recorder",
            f"Đã xuất DOCX ({self.rec.step_count} bước):\n{saved}", parent=self)

    # ---- lưu / mở dự án ----
    def _refresh_title_bar(self):
        name = os.path.basename(self.rec.project_path) if self.rec.project_path else ""
        self.title("Xem lại & chỉnh sửa" + (f" — {name}" if name else ""))

    def _save_project(self, force_dialog: bool = False):
        self._sync_to_steps()
        if self.rec.step_count == 0:
            messagebox.showinfo("Steps Recorder", "Không còn bước nào để lưu.", parent=self)
            return
        path = self.rec.project_path if (self.rec.project_path and not force_dialog) else None
        if not path:
            base = (self.rec.report_title or "steps").strip()
            safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in base)[:40].strip()
            default = f"{safe or 'steps'}_{dt.datetime.now():%Y%m%d_%H%M%S}.steps.json"
            path = filedialog.asksaveasfilename(
                defaultextension=".steps.json", initialfile=default,
                filetypes=PROJECT_FILETYPES, parent=self)
        if not path:
            return
        try:
            saved = self.rec.save_project(path)
            self._refresh_title_bar()
            self.status.set(f"{self.rec.step_count} bước · đã lưu dự án")
            messagebox.showinfo(
                "Steps Recorder",
                f"Đã lưu dự án (có thể mở lại sau):\n{saved}", parent=self)
        except Exception as e:
            messagebox.showerror("Steps Recorder", f"Lưu dự án thất bại:\n{e}", parent=self)

    def _open_project(self):
        path = filedialog.askopenfilename(
            filetypes=PROJECT_FILETYPES, parent=self)
        if not path:
            return
        try:
            self.rec.load_project(path)
        except Exception as e:
            messagebox.showerror("Steps Recorder", f"Mở dự án thất bại:\n{e}", parent=self)
            return
        self.var_title.set(self.rec.report_title)
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", self.rec.report_summary)
        self._backup = None
        self.btn_undo.config(state="disabled")
        self._render_steps()
        self._refresh_title_bar()
        self.status.set(f"{self.rec.step_count} bước · đã mở dự án")

    # ---- xử lý AI (chạy nền) ----
    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.btn_ai.config(state=state)
        self.btn_ai_html.config(state=state)

    def _check_ai_config(self) -> bool:
        cfg = self.config_obj
        if not (cfg.base_url or "").strip() or not (cfg.model or "").strip():
            messagebox.showwarning(
                "AI",
                "Chưa cấu hình Base URL / Model.\n"
                "Mở ⚙ Cấu hình (vLLM: http://host:8000/v1 + tên model).",
                parent=self)
            return False
        return True

    def _run_ai(self):
        self._sync_to_steps()
        cfg = self.config_obj
        if not self._check_ai_config() or self.rec.step_count == 0:
            return
        # snapshot cho Hoàn tác
        self._backup = (copy.deepcopy(self.rec.steps),
                        self.rec.report_title, self.rec.report_summary)
        self._merge_flag = bool(cfg.ai_merge_steps)
        self.status.set("AI đang biên soạn hướng dẫn…")
        self._set_busy(True)
        steps_snapshot = list(self.rec.steps)

        def worker():
            try:
                result = call_ai(cfg, steps_snapshot)
                self.after(0, lambda: self._ai_done(result))
            except Exception as e:
                self.after(0, lambda err=e: self._ai_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _ai_done(self, result):
        apply_ai_result(self.rec, result, merge=self._merge_flag)
        self.var_title.set(self.rec.report_title)
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", self.rec.report_summary)
        self._render_steps()
        self._set_busy(False)
        self.btn_undo.config(state="normal")
        self.status.set(f"{self.rec.step_count} bước · AI đã biên soạn")

    def _undo_ai(self):
        if not self._backup:
            return
        steps, title, summary = self._backup
        self.rec.steps = copy.deepcopy(steps)
        self.rec.report_title = title
        self.rec.report_summary = summary
        self.var_title.set(title)
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", summary)
        self._render_steps()
        self.btn_undo.config(state="disabled")
        self.status.set(f"{self.rec.step_count} bước · đã hoàn tác AI")

    def _ai_error(self, err):
        self._set_busy(False)
        self.status.set(f"{self.rec.step_count} bước")
        messagebox.showerror("AI", f"Xử lý AI thất bại:\n{err}", parent=self)

    # ---- AI tạo HTML trực quan (chạy nền) ----
    def _run_ai_html(self):
        self._sync_to_steps()
        if not self._check_ai_config() or self.rec.step_count == 0:
            return
        cfg = self.config_obj
        self.status.set("🎨 AI đang thiết kế trang HTML…")
        self._set_busy(True)
        steps_snapshot = list(self.rec.steps)
        title = self.rec.report_title
        summary = self.rec.report_summary

        def progress(round_no, max_rounds):
            # chạy trên luồng worker -> chuyển về luồng Tk
            msg = (f"🎨 AI đang thiết kế trang HTML… "
                   f"(lượt {round_no}/{max_rounds})")
            self.after(0, lambda: self.status.set(msg))

        def worker():
            try:
                html = call_ai_html(cfg, steps_snapshot,
                                    title=title, summary=summary,
                                    on_progress=progress)
                self.after(0, lambda: self._ai_html_done(html))
            except Exception as e:
                self.after(0, lambda err=e: self._ai_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _ai_html_done(self, html: str):
        self._set_busy(False)
        self.status.set(f"{self.rec.step_count} bước · AI đã tạo HTML")
        default = f"steps_ai_{dt.datetime.now():%Y%m%d_%H%M%S}.html"
        path = filedialog.asksaveasfilename(
            defaultextension=".html", initialfile=default,
            filetypes=[("HTML", "*.html")], parent=self)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            messagebox.showerror(
                "Steps Recorder", f"Không lưu được file:\n{e}", parent=self)
            return
        try:
            webbrowser.open(f"file://{os.path.abspath(path)}")
        except Exception:
            pass
        messagebox.showinfo(
            "Steps Recorder",
            f"AI đã tạo trang HTML trực quan:\n{path}", parent=self)

