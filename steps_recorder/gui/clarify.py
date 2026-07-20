"""Trợ lý hỏi làm rõ: hộp thoại câu hỏi + bộ điều phối pha hỏi trước biên soạn.

Giống cách một trợ lý (Claude) làm việc: xem yêu cầu, còn gì chưa rõ thì hỏi
lại người dùng, nhận câu trả lời rồi mới bắt tay biên soạn. Pha hỏi là phụ
trợ — mọi lỗi ở pha này chỉ ghi log và biên soạn tiếp như bình thường.
"""
import logging
import threading
import tkinter as tk
from tkinter import ttk

from ..ai import MAX_CLARIFY_ROUNDS, call_ai_questions
from .theme import UITheme, _apply_ttk_theme, _btn, _ui_font

log = logging.getLogger("steps_recorder")


class ClarifyDialog(tk.Toplevel):
    """Hiện các câu hỏi của AI; result = [(hỏi, đáp)] hoặc None nếu bỏ qua."""

    def __init__(self, parent, questions):
        super().__init__(parent)
        self.title("Trợ lý cần làm rõ")
        self.result = None
        self.configure(bg=UITheme.BG)
        _apply_ttk_theme(self)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._skip)

        header = tk.Frame(self, bg=UITheme.BRAND)
        header.pack(fill="x")
        tk.Label(header, text="💬 AI cần làm rõ vài điểm", bg=UITheme.BRAND,
                 fg="#ffffff", font=_ui_font(13, "bold")).pack(
            anchor="w", padx=18, pady=(14, 2))
        tk.Label(header,
                 text="Trả lời (hoặc bỏ trống câu không rõ) để tài liệu chính xác hơn.",
                 bg=UITheme.BRAND, fg="#cfe2f7",
                 font=_ui_font(UITheme.FONT_SMALL)).pack(
            anchor="w", padx=18, pady=(0, 12))

        body = tk.Frame(self, bg=UITheme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        self._fields = []  # [(câu hỏi, StringVar)]
        for q in questions:
            card = tk.Frame(body, bg=UITheme.SURFACE, highlightthickness=1,
                            highlightbackground=UITheme.BORDER)
            card.pack(fill="x", pady=(0, 8))
            tk.Label(card, text=q["question"], bg=UITheme.SURFACE,
                     fg=UITheme.TEXT, font=_ui_font(weight="bold"),
                     wraplength=520, justify="left").pack(
                anchor="w", padx=12, pady=(10, 4))
            var = tk.StringVar()
            sugg = q.get("suggestions") or []
            if sugg:
                widget = ttk.Combobox(card, textvariable=var, values=sugg,
                                      width=58)
            else:
                widget = tk.Entry(card, textvariable=var, width=60,
                                  bg=UITheme.SURFACE_2, fg=UITheme.TEXT,
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=UITheme.BORDER,
                                  font=_ui_font())
            widget.pack(fill="x", padx=12, pady=(0, 10))
            self._fields.append((q["question"], var))

        bar = tk.Frame(self, bg=UITheme.BG)
        bar.pack(fill="x", padx=16, pady=(0, 14))
        _btn(bar, "Bỏ qua, biên soạn luôn", command=self._skip,
             variant="ghost").pack(side="left")
        _btn(bar, "✔ Gửi câu trả lời", command=self._submit,
             variant="primary").pack(side="right")

        if self._fields:
            self.after(100, lambda: self.focus_force())

    def _submit(self):
        answers = [(q, v.get().strip()) for q, v in self._fields
                   if v.get().strip()]
        # gửi mà không trả lời gì thì coi như bỏ qua
        self.result = answers or None
        self.destroy()

    def _skip(self):
        self.result = None
        self.destroy()


def run_clarify_flow(parent, cfg, steps, set_status, on_done):
    """Chạy pha hỏi làm rõ rồi gọi on_done(qa) trên luồng Tk.

    qa là danh sách (câu hỏi, trả lời) đã thu được (có thể rỗng). Tối đa
    MAX_CLARIFY_ROUNDS lượt hỏi; AI trả về danh sách rỗng hoặc người dùng
    bỏ qua thì sang biên soạn ngay.
    """
    qa = []
    state = {"round": 0}

    def next_round():
        state["round"] += 1
        if (not getattr(cfg, "ai_ask_questions", True)
                or state["round"] > MAX_CLARIFY_ROUNDS):
            on_done(qa)
            return
        set_status(f"💬 AI đang xem có gì cần hỏi… (lượt {state['round']})")

        def worker():
            try:
                qs = call_ai_questions(cfg, steps, qa)
            except Exception:
                log.warning("Pha hỏi làm rõ lỗi — biên soạn không cần hỏi",
                            exc_info=True)
                qs = []
            parent.after(0, lambda: got(qs))

        threading.Thread(target=worker, daemon=True).start()

    def got(questions):
        if not questions:
            on_done(qa)
            return
        dlg = ClarifyDialog(parent, questions)
        parent.wait_window(dlg)
        if not dlg.result:
            on_done(qa)  # người dùng bỏ qua -> không hỏi thêm
            return
        qa.extend(dlg.result)
        next_round()

    next_round()
