"""Theme giao diện và các widget helper dùng chung."""
import tkinter as tk
from tkinter import ttk


class UITheme:
    BG = "#f0f4f8"
    SURFACE = "#ffffff"
    SURFACE_2 = "#f7fafc"
    BORDER = "#d8e0ea"
    BORDER_SOFT = "#e8eef5"
    TEXT = "#1a2332"
    MUTED = "#64748b"
    BRAND = "#0b5cab"
    BRAND_HOVER = "#0a4d8c"
    BRAND_SOFT = "#e8f1fb"
    ACCENT = "#7c3aed"
    ACCENT_SOFT = "#f3e8ff"
    DANGER = "#dc2626"
    DANGER_SOFT = "#fef2f2"
    SUCCESS = "#059669"
    RECORD = "#e11d48"
    RECORD_SOFT = "#fff1f2"
    WARNING = "#d97706"
    FONT = "Segoe UI"
    FONT_SIZE = 10
    FONT_TITLE = 16
    FONT_HEAD = 12
    FONT_SMALL = 9


def _ui_font(size=None, weight="normal"):
    return (UITheme.FONT, size or UITheme.FONT_SIZE, weight)


def _style_entry(widget, **kw):
    opts = dict(
        relief="flat",
        highlightthickness=1,
        highlightbackground=UITheme.BORDER,
        highlightcolor=UITheme.BRAND,
        bg=UITheme.SURFACE,
        fg=UITheme.TEXT,
        insertbackground=UITheme.TEXT,
        font=_ui_font(),
    )
    opts.update(kw)
    widget.configure(**opts)
    return widget


def _style_text(widget, **kw):
    opts = dict(
        relief="flat",
        highlightthickness=1,
        highlightbackground=UITheme.BORDER,
        highlightcolor=UITheme.BRAND,
        bg=UITheme.SURFACE,
        fg=UITheme.TEXT,
        insertbackground=UITheme.TEXT,
        font=_ui_font(),
        padx=8,
        pady=6,
        wrap="word",
    )
    opts.update(kw)
    widget.configure(**opts)
    return widget


def _btn(parent, text, command=None, variant="secondary", width=None, state="normal"):
    """Nút phẳng hiện đại: primary | secondary | danger | accent | ghost | record."""
    styles = {
        "primary":  (UITheme.BRAND, "#ffffff", UITheme.BRAND_HOVER),
        "secondary": (UITheme.SURFACE, UITheme.TEXT, UITheme.BRAND_SOFT),
        "danger":   (UITheme.DANGER_SOFT, UITheme.DANGER, "#fee2e2"),
        "accent":   (UITheme.ACCENT, "#ffffff", "#6d28d9"),
        "ghost":    (UITheme.SURFACE_2, UITheme.MUTED, UITheme.BORDER_SOFT),
        "record":   (UITheme.RECORD, "#ffffff", "#be123c"),
        "success":  (UITheme.SUCCESS, "#ffffff", "#047857"),
    }
    bg, fg, hover = styles.get(variant, styles["secondary"])
    btn = tk.Button(
        parent, text=text, command=command, state=state,
        bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, cursor="hand2",
        font=_ui_font(UITheme.FONT_SIZE, "bold" if variant in ("primary", "record", "accent") else "normal"),
        padx=12, pady=7,
        highlightthickness=1 if variant == "secondary" else 0,
        highlightbackground=UITheme.BORDER if variant == "secondary" else bg,
    )
    if width is not None:
        btn.configure(width=width)
    return btn


def _label(parent, text="", *, muted=False, bold=False, size=None, **kw):
    return tk.Label(
        parent, text=text,
        bg=kw.pop("bg", UITheme.SURFACE if "bg" not in kw else kw.get("bg")),
        fg=UITheme.MUTED if muted else UITheme.TEXT,
        font=_ui_font(size, "bold" if bold else "normal"),
        **kw,
    )


def _section_card(parent, title=None, subtitle=None):
    """Card trắng bo viền, tùy chọn tiêu đề phần."""
    outer = tk.Frame(parent, bg=UITheme.BG)
    card = tk.Frame(outer, bg=UITheme.SURFACE, highlightthickness=1,
                    highlightbackground=UITheme.BORDER)
    card.pack(fill="both", expand=True)
    if title:
        head = tk.Frame(card, bg=UITheme.SURFACE)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text=title, bg=UITheme.SURFACE, fg=UITheme.BRAND,
                 font=_ui_font(UITheme.FONT_HEAD, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(head, text=subtitle, bg=UITheme.SURFACE, fg=UITheme.MUTED,
                     font=_ui_font(UITheme.FONT_SMALL)).pack(anchor="w", pady=(2, 0))
    body = tk.Frame(card, bg=UITheme.SURFACE)
    body.pack(fill="both", expand=True, padx=16, pady=(8 if title else 14, 14))
    return outer, body


def _apply_ttk_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "TCombobox",
        fieldbackground=UITheme.SURFACE,
        background=UITheme.SURFACE,
        foreground=UITheme.TEXT,
        arrowcolor=UITheme.BRAND,
        bordercolor=UITheme.BORDER,
        lightcolor=UITheme.BORDER,
        darkcolor=UITheme.BORDER,
        padding=6,
        font=_ui_font(),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", UITheme.SURFACE)],
        selectbackground=[("readonly", UITheme.BRAND_SOFT)],
        selectforeground=[("readonly", UITheme.TEXT)],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=UITheme.BORDER,
        troughcolor=UITheme.SURFACE_2,
        bordercolor=UITheme.SURFACE_2,
        arrowcolor=UITheme.MUTED,
        relief="flat",
    )

