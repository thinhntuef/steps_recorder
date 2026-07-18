"""Hộp thoại Cấu hình (AI, nhập/xuất cấu hình)."""
import datetime as dt
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import CONFIG_FILETYPES, CONFIG_PATH, PRESETS, AppConfig
from .theme import (UITheme, _apply_ttk_theme, _btn, _section_card,
                    _style_entry, _style_text, _ui_font)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config: AppConfig, on_saved=None):
        super().__init__(parent)
        self.title("Cấu hình")
        self.config_obj = config
        self.on_saved = on_saved
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=UITheme.BG)
        _apply_ttk_theme(self)

        # Header
        header = tk.Frame(self, bg=UITheme.BRAND)
        header.pack(fill="x")
        tk.Label(header, text="Cấu hình trợ lý AI", bg=UITheme.BRAND, fg="#ffffff",
                 font=_ui_font(14, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(header,
                 text="OpenAI-compatible / vLLM  ·  Base URL dạng http://host:8000/v1",
                 bg=UITheme.BRAND, fg="#cfe2f7",
                 font=_ui_font(UITheme.FONT_SMALL)).pack(anchor="w", padx=20, pady=(0, 14))

        wrap = tk.Frame(self, bg=UITheme.BG)
        wrap.pack(fill="both", expand=True, padx=16, pady=16)

        card, frm = _section_card(wrap, "Kết nối & mô hình")
        card.pack(fill="x", pady=(0, 10))
        frm.columnconfigure(1, weight=1)

        pad = {"padx": (0, 10), "pady": 5}

        def row(r, label, widget):
            tk.Label(frm, text=label, bg=UITheme.SURFACE, fg=UITheme.MUTED,
                     font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(
                row=r, column=0, sticky="w", **pad)
            widget.grid(row=r, column=1, sticky="ew", pady=5)

        self.var_base = tk.StringVar(value=config.base_url)
        self.var_model = tk.StringVar(value=config.model)
        self.var_key = tk.StringVar(value=config.api_key)
        self.var_lang = tk.StringVar(value=config.out_language)
        self.var_vision = tk.BooleanVar(value=config.use_vision)
        self.var_merge = tk.BooleanVar(value=config.ai_merge_steps)
        self.var_preset = tk.StringVar(value=config.preset)

        e_base = _style_entry(tk.Entry(frm, textvariable=self.var_base, width=46))
        e_model = _style_entry(tk.Entry(frm, textvariable=self.var_model, width=46))
        e_key = _style_entry(tk.Entry(frm, textvariable=self.var_key, show="*", width=46))
        row(0, "Base URL", e_base)
        row(1, "Model", e_model)
        row(2, "API Key", e_key)

        card2, frm2 = _section_card(wrap, "Biên soạn tài liệu")
        card2.pack(fill="x", pady=(0, 10))
        frm2.columnconfigure(1, weight=1)

        tk.Label(frm2, text="Mục đích (preset)", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Combobox(frm2, textvariable=self.var_preset,
                     values=list(PRESETS.keys()), state="readonly", width=44).grid(
            row=0, column=1, sticky="ew", pady=5)

        tk.Label(frm2, text="Yêu cầu thêm", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(
            row=1, column=0, sticky="nw", padx=(0, 10), pady=5)
        self.txt_prompt = _style_text(tk.Text(frm2, width=46, height=4))
        self.txt_prompt.insert("1.0", config.custom_prompt)
        self.txt_prompt.grid(row=1, column=1, sticky="ew", pady=5)

        tk.Label(frm2, text="Ngôn ngữ đầu ra", bg=UITheme.SURFACE, fg=UITheme.MUTED,
                 font=_ui_font(UITheme.FONT_SMALL, "bold")).grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        _style_entry(tk.Entry(frm2, textvariable=self.var_lang, width=46)).grid(
            row=2, column=1, sticky="ew", pady=5)

        opts = tk.Frame(frm2, bg=UITheme.SURFACE_2, highlightthickness=1,
                        highlightbackground=UITheme.BORDER_SOFT)
        opts.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        tk.Checkbutton(
            opts, text="Gửi kèm ảnh cho AI (vision) — cần model hỗ trợ ảnh (vd VLM)",
            variable=self.var_vision, bg=UITheme.SURFACE_2, fg=UITheme.TEXT,
            activebackground=UITheme.SURFACE_2, selectcolor=UITheme.SURFACE,
            font=_ui_font(), anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))
        tk.Checkbutton(
            opts, text="Cho phép AI gộp/bỏ bước (biên soạn gọn như tài liệu chính thức)",
            variable=self.var_merge, bg=UITheme.SURFACE_2, fg=UITheme.TEXT,
            activebackground=UITheme.SURFACE_2, selectcolor=UITheme.SURFACE,
            font=_ui_font(), anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 10))

        bar = tk.Frame(wrap, bg=UITheme.BG)
        bar.pack(fill="x", pady=(4, 0))
        _btn(bar, "Xuất cấu hình", command=self._export_config,
             variant="ghost", width=14).pack(side="left")
        _btn(bar, "Nhập cấu hình", command=self._import_config,
             variant="ghost", width=14).pack(side="left", padx=(6, 0))
        _btn(bar, "Đóng", command=self.destroy, variant="ghost", width=10).pack(
            side="right", padx=(6, 0))
        _btn(bar, "Lưu cấu hình", command=self._save, variant="primary", width=14).pack(
            side="right")

    def _apply_form_to_config(self):
        c = self.config_obj
        c.base_url = self.var_base.get().strip() or "https://api.openai.com/v1"
        c.model = self.var_model.get().strip() or "gpt-4o-mini"
        c.api_key = self.var_key.get().strip()
        c.out_language = self.var_lang.get().strip() or "Tiếng Việt"
        c.use_vision = bool(self.var_vision.get())
        c.ai_merge_steps = bool(self.var_merge.get())
        c.preset = self.var_preset.get()
        c.custom_prompt = self.txt_prompt.get("1.0", "end").strip()

    def _load_form_from_config(self):
        c = self.config_obj
        self.var_base.set(c.base_url)
        self.var_model.set(c.model)
        self.var_key.set(c.api_key)
        self.var_lang.set(c.out_language)
        self.var_vision.set(bool(c.use_vision))
        self.var_merge.set(bool(c.ai_merge_steps))
        self.var_preset.set(c.preset if c.preset in PRESETS else "Hướng dẫn sử dụng")
        self.txt_prompt.delete("1.0", "end")
        self.txt_prompt.insert("1.0", c.custom_prompt or "")

    def _export_config(self):
        self._apply_form_to_config()
        default = f"steps_recorder_{dt.datetime.now():%Y%m%d_%H%M%S}.config.json"
        path = filedialog.asksaveasfilename(
            defaultextension=".config.json", initialfile=default,
            filetypes=CONFIG_FILETYPES, parent=self)
        if not path:
            return
        include_key = False
        if (self.config_obj.api_key or "").strip():
            include_key = messagebox.askyesno(
                "Cấu hình",
                "Mặc định KHÔNG xuất API key (an toàn khi chia sẻ).\n\n"
                "Bạn có muốn GỒM API key trong file không?\n"
                "(Chỉ chọn Có nếu file chỉ dùng riêng, không gửi cho người khác.)",
                parent=self)
        try:
            saved = self.config_obj.export_to(path, include_api_key=include_key)
            note = " (có API key)" if include_key else " (đã ẩn API key)"
            messagebox.showinfo(
                "Cấu hình", f"Đã xuất cấu hình{note}:\n{saved}", parent=self)
        except Exception as e:
            messagebox.showerror("Cấu hình", f"Xuất cấu hình thất bại:\n{e}", parent=self)

    def _import_config(self):
        path = filedialog.askopenfilename(filetypes=CONFIG_FILETYPES, parent=self)
        if not path:
            return
        try:
            self.config_obj.import_from(path)
            self._load_form_from_config()
            messagebox.showinfo(
                "Cấu hình",
                "Đã nhập cấu hình vào form.\nBấm «Lưu cấu hình» để áp dụng lâu dài.",
                parent=self)
        except Exception as e:
            messagebox.showerror("Cấu hình", f"Nhập cấu hình thất bại:\n{e}", parent=self)

    def _save(self):
        self._apply_form_to_config()
        if not self.config_obj.save():
            messagebox.showwarning(
                "Cấu hình",
                "KHÔNG lưu được file cấu hình:\n"
                f"{CONFIG_PATH}\n\nCấu hình chỉ áp dụng cho phiên này.",
                parent=self)
        else:
            messagebox.showinfo("Cấu hình", "Đã lưu cấu hình.", parent=self)
        if self.on_saved:
            self.on_saved()
        self.destroy()

