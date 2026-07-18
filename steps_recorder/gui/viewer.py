"""Cửa sổ xem ảnh phóng to (cuộn + zoom)."""
import base64
import io
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image

from ..deps import _HAS_IMAGETK, ImageTk
from .theme import UITheme, _btn, _ui_font


class ImageViewer(tk.Toplevel):
    def __init__(self, parent, b64: str, title: str = "Xem ảnh"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=UITheme.BG)
        self.geometry("1000x720")
        self.minsize(480, 360)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._pil = None
        self._photo = None
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 8.0

        try:
            self._pil = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        except Exception as e:
            messagebox.showerror("Xem ảnh", f"Không mở được ảnh:\n{e}", parent=parent)
            self.destroy()
            return

        bar = tk.Frame(self, bg=UITheme.BG)
        bar.pack(fill="x", padx=12, pady=(10, 6))
        _btn(bar, "−", command=lambda: self._zoom_by(0.8), variant="ghost", width=4).pack(
            side="left", padx=2)
        _btn(bar, "+", command=lambda: self._zoom_by(1.25), variant="ghost", width=4).pack(
            side="left", padx=2)
        _btn(bar, "100%", command=self._zoom_100, variant="secondary", width=6).pack(
            side="left", padx=2)
        _btn(bar, "Vừa khung", command=self._zoom_fit, variant="secondary", width=10).pack(
            side="left", padx=2)
        self._zoom_lbl = tk.Label(bar, text="100%", bg=UITheme.BG, fg=UITheme.MUTED,
                                  font=_ui_font(UITheme.FONT_SMALL))
        self._zoom_lbl.pack(side="left", padx=10)
        _btn(bar, "Đóng", command=self.destroy, variant="ghost", width=8).pack(side="right")

        body = tk.Frame(self, bg=UITheme.SURFACE, highlightthickness=1,
                        highlightbackground=UITheme.BORDER)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.canvas = tk.Canvas(body, bg=UITheme.SURFACE_2, highlightthickness=0)
        hsb = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Configure>", lambda e: self._on_canvas_configure())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.bind("<plus>", lambda e: self._zoom_by(1.25))
        self.bind("<minus>", lambda e: self._zoom_by(0.8))
        self.bind("<Escape>", lambda e: self.destroy())

        self.after(50, self._zoom_fit)

    def _on_canvas_configure(self):
        if self._photo is None and self._pil is not None:
            self._zoom_fit()

    def _on_wheel(self, e):
        if e.state & 0x4:  # Ctrl
            self._on_ctrl_wheel(e)
            return
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_ctrl_wheel(self, e):
        self._zoom_by(1.25 if e.delta > 0 else 0.8)

    def _zoom_by(self, factor: float):
        self._set_zoom(self._zoom * factor)

    def _zoom_100(self):
        self._set_zoom(1.0)

    def _zoom_fit(self):
        if self._pil is None:
            return
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        iw, ih = self._pil.size
        if iw <= 0 or ih <= 0:
            return
        z = min(cw / iw, ch / ih) * 0.98
        self._set_zoom(max(z, self._min_zoom))

    def _set_zoom(self, z: float):
        if self._pil is None or not _HAS_IMAGETK:
            return
        z = max(self._min_zoom, min(self._max_zoom, z))
        self._zoom = z
        iw, ih = self._pil.size
        nw = max(1, int(iw * z))
        nh = max(1, int(ih * z))
        try:
            resized = self._pil.resize((nw, nh), Image.Resampling.LANCZOS)
        except Exception:
            resized = self._pil.resize((nw, nh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, nw, nh))
        self._zoom_lbl.configure(text=f"{int(round(z * 100))}%")

