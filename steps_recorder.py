"""
Steps Recorder (bản Python) — ghi lại các bước thao tác của người dùng.

Mô phỏng công cụ "Steps Recorder / Problem Steps Recorder (PSR)" của Windows,
có bổ sung:
  - Lắng nghe click chuột và phím gõ, chụp màn hình khoanh tròn vị trí con trỏ.
  - Gộp phím gõ liên tiếp thành một bước "Nhập văn bản".
  - Cửa sổ XEM LẠI & CHỈNH SỬA sau khi ghi: xoá bước, xoá bớt ảnh, sửa nhãn/mô
    tả, sửa tiêu đề/tóm tắt trước khi xuất.
   - Trợ lý AI (OpenAI-compatible / vLLM): biên soạn lại thành hướng dẫn sử
     dụng chuyên nghiệp (nhãn, mô tả, tiêu đề, tóm tắt; chia phần mục lục;
     tuỳ chọn gộp/bỏ bước).
   - Xuất báo cáo HTML tự chứa (ảnh nhúng base64), mục lục theo phần + bước.
   - Lưu / mở lại dự án (.steps.json) để tiếp tục chỉnh sửa sau.
 
 Cài đặt phụ thuộc:
     pip install pynput pillow mss pygetwindow
 Tính năng AI gọi API qua urllib (thư viện chuẩn) nên KHÔNG cần cài thêm.
 
 Chạy:
     python steps_recorder.py
 
 Cấu hình AI: bấm nút "⚙ Cấu hình" trong cửa sổ chính.
 """

import base64
import io
import os
import copy
import json
import time
import threading
import datetime as dt
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# --- Thư viện bên thứ ba (báo lỗi rõ ràng nếu thiếu) --------------------------
try:
    from pynput import mouse, keyboard
except ImportError:
    raise SystemExit("Thiếu 'pynput'. Cài bằng: pip install pynput")

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("Thiếu 'Pillow'. Cài bằng: pip install pillow")

try:
    from PIL import ImageTk  # hiển thị thumbnail trong cửa sổ chỉnh sửa
    _HAS_IMAGETK = True
except Exception:
    _HAS_IMAGETK = False

try:
    import mss  # chụp màn hình nhanh, đa nền tảng
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False
    from PIL import ImageGrab  # dự phòng (Windows/macOS)

try:
    import pygetwindow as gw  # lấy tiêu đề cửa sổ active
    _HAS_GW = True
except ImportError:
    _HAS_GW = False


# --- Cấu trúc một bước --------------------------------------------------------
@dataclass
class Step:
    index: int
    timestamp: str
    action: str                       # NHÃN: mô tả hành động (một dòng)
    window: str                       # tiêu đề cửa sổ active
    description: str = ""             # MÔ TẢ dài (AI sinh + người dùng sửa)
    section: str = ""                 # TÊN PHẦN trong mục lục (AI gán / người sửa)
    images: List[str] = field(default_factory=list)  # danh sách ảnh PNG base64

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "window": self.window,
            "description": self.description,
            "section": self.section,
            "images": list(self.images),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        imgs = d.get("images") or []
        if not isinstance(imgs, list):
            imgs = []
        return cls(
            index=int(d.get("index") or 0),
            timestamp=str(d.get("timestamp") or ""),
            action=str(d.get("action") or ""),
            window=str(d.get("window") or ""),
            description=str(d.get("description") or ""),
            section=str(d.get("section") or ""),
            images=[str(x) for x in imgs if x],
        )


PROJECT_FORMAT = "steps_recorder_project"
PROJECT_VERSION = 1
PROJECT_FILETYPES = [
    ("Dự án Steps Recorder", "*.steps.json"),
    ("JSON", "*.json"),
    ("Tất cả", "*.*"),
]
CONFIG_FILETYPES = [
    ("Cấu hình Steps Recorder", "*.config.json"),
    ("JSON", "*.json"),
    ("Tất cả", "*.*"),
]


# --- Cấu hình ứng dụng --------------------------------------------------------
CONFIG_PATH = os.path.expanduser("~/.steps_recorder_config.json")

# Mục đích sử dụng -> đoạn ngữ cảnh gắn vào system prompt của AI
PRESETS = {
    "Hướng dẫn sử dụng":
        "Biên soạn như NHÂN VIÊN TÀI LIỆU chuyên nghiệp viết HƯỚNG DẪN SỬ DỤNG "
        "cho người dùng cuối (user guide / how-to).\n"
        "- Giọng văn: trang trọng, rõ ràng, mệnh lệnh lịch sự (\"Nhấp…\", "
        "\"Chọn…\", \"Nhập…\", \"Kiểm tra…\").\n"
        "- Mỗi bước: (1) label = tiêu đề hành động ngắn (không toạ độ chuột, "
        "không kỹ thuật thô); (2) description = hướng dẫn chi tiết: thao tác "
        "cần làm, vị trí/UI liên quan (nút, menu, ô nhập…), dữ liệu cần nhập "
        "(dạng ví dụ/placeholder), và kết quả mong đợi sau bước.\n"
        "- Gộp click + gõ phím cùng một thao tác logic thành MỘT bước (vd: "
        "\"Nhập tên đăng nhập\" thay vì click ô rồi gõ).\n"
        "- Bỏ bước nhiễu (click nhầm, focus vô ích, phím đặc biệt không liên "
        "quan) nếu không cần cho người đọc.\n"
        "- title: tên tài liệu hướng dẫn (không ghi \"Bản ghi…\").\n"
        "- summary: mở đầu ngắn gồm mục đích, đối tượng, điều kiện tiên quyết "
        "(nếu suy ra được), và kết quả cuối cùng khi hoàn tất.",
    "Báo lỗi / Bug report":
        "Viết như báo cáo lỗi chuyên nghiệp: các bước tái hiện tuần tự, điều "
        "kiện ban đầu, kết quả quan sát; làm nổi bật thao tác/kết quả bất "
        "thường. label ngắn; description ghi rõ kỳ vọng vs thực tế nếu suy "
        "được.",
    "Quy trình SOP":
        "Viết như quy trình chuẩn (SOP): bước đánh số, mệnh lệnh ngắn gọn, "
        "có thể lặp lại và kiểm soát; mỗi description nêu hành động + tiêu "
        "chí hoàn thành bước.",
    "Tài liệu đào tạo":
        "Viết như tài liệu đào tạo: giải thích vì sao mỗi bước cần thiết, "
        "gợi ý lưu ý cho người mới; giọng thân thiện nhưng vẫn chuẩn mực.",
    "Tuỳ chỉnh (tự do)": "",
}


@dataclass
class AppConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""                 # WARNING: lưu PLAINTEXT trong file cấu hình ở home
    use_vision: bool = False
    preset: str = "Hướng dẫn sử dụng"
    custom_prompt: str = ""
    out_language: str = "Tiếng Việt"
    ai_merge_steps: bool = True       # cho AI gộp/bỏ bước
    export_toc: bool = True           # xuất HTML kèm mục lục

    def to_dict(self, include_api_key: bool = True) -> dict:
        data = asdict(self)
        if not include_api_key:
            data["api_key"] = ""
        return data

    def apply_dict(self, data: dict, keep_api_key_if_empty: bool = False):
        if not isinstance(data, dict):
            return
        prev_key = self.api_key
        for k, v in data.items():
            if hasattr(self, k):  # bỏ qua khoá lạ (vd chrome_* của bản cũ)
                setattr(self, k, v)
        if keep_api_key_if_empty:
            imported = (self.api_key or "").strip()
            # Bỏ qua key trống / placeholder che (*** / REDACTED)
            if not imported or imported in ("***", "REDACTED", "<redacted>"):
                self.api_key = prev_key
        if self.preset not in PRESETS:
            self.preset = "Hướng dẫn sử dụng"

    @classmethod
    def load(cls) -> "AppConfig":
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = cls()
            cfg.apply_dict(data)
            return cfg
        except Exception:
            return cls()

    def save(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(include_api_key=True), f,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    def export_to(self, path: str, include_api_key: bool = False) -> str:
        """Xuất JSON chia sẻ. Mặc định KHÔNG ghi api_key (tránh lộ secret)."""
        if not path.lower().endswith((".json", ".config.json")):
            path = path + ".config.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(include_api_key=include_api_key), f,
                      ensure_ascii=False, indent=2)
        return path

    def import_from(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("File cấu hình không hợp lệ.")
        # Giữ key hiện tại nếu file xuất không có / đã che key
        self.apply_dict(data, keep_api_key_if_empty=True)


# --- Lớp AI (hàm thuần, tách khỏi GUI để dễ kiểm thử) ------------------------
def _system_prompt(cfg: AppConfig) -> str:
    parts = [
        "Bạn là chuyên viên biên soạn tài liệu kỹ thuật (Technical Writer) "
        "chuyên nghiệp. Nhiệm vụ: biến nhật ký thô (click chuột, phím gõ, "
        "tiêu đề cửa sổ, ảnh màn hình) thành tài liệu hướng dẫn mạch lạc, "
        "dễ làm theo, trình bày như bản phát hành chính thức.",
        "",
        "NGUYÊN TẮC BIÊN SOẠN:",
        "1. Chuyển thao tác kỹ thuật thô thành ngôn ngữ người dùng cuối. "
        "Ví dụ: 'Nhấp chuột trái tại (412, 280)' → 'Nhấp nút Đăng nhập' "
        "(suy từ ngữ cảnh cửa sổ/ảnh/văn bản gõ nếu có).",
        "2. KHÔNG đưa toạ độ pixel, tên class UI, hay log kỹ thuật vào tài liệu.",
        "3. Ẩn/thay thông tin nhạy cảm (tên người, tài khoản, mật khẩu, số "
        "điện thoại, email, mã nội bộ…) bằng vai trò hoặc placeholder "
        "(vd: 'tài khoản người dùng', 'mật khẩu của bạn', '[Họ tên]').",
        "4. label: một dòng, ngắn gọn (≤ 12 từ), dạng động từ + đối tượng "
        "(vd: 'Mở form tạo hồ sơ').",
        "5. description: 2–5 câu hoặc gạch đầu dòng ngắn; nêu rõ: làm gì, "
        "ở đâu trên giao diện, nhập gì (nếu có), kết quả/kiểm tra sau bước.",
        "6. title: tên tài liệu chuyên nghiệp, phản ánh quy trình (không "
        "dùng 'Bản ghi các bước').",
        "7. summary: đoạn mở đầu 3–6 câu: mục đích, đối tượng, điều kiện "
        "tiên quyết (nếu có), kết quả khi hoàn tất.",
        "8. Giữ thứ tự logic thời gian; không bịa tính năng không có trong "
        "dữ liệu đầu vào. Nếu không chắc UI element, mô tả theo hành động "
        "quan sát được + cửa sổ active.",
        "9. CHIA PHẦN (section): nhóm các bước liên quan thành các PHẦN "
        "trong mục lục (vd: 'Đăng nhập', 'Tạo hồ sơ', 'Xuất báo cáo'). "
        "Mỗi bước có 'section' = tên phần ngắn (≤ 8 từ). Các bước cùng "
        "một giai đoạn logic dùng CÙNG tên section; đổi section khi sang "
        "giai đoạn mới. Nên có 2–8 phần tùy độ dài quy trình; không để "
        "mọi bước chung một phần nếu quy trình có nhiều giai đoạn rõ rệt.",
    ]
    if cfg.use_vision:
        parts.append(
            "10. Ảnh đính kèm có vòng đỏ khoanh vị trí click — dùng để nhận "
            "diện nút/ô/menu và viết mô tả chính xác hơn.")
    if cfg.ai_merge_steps:
        parts.append(
            "BẠN ĐƯỢC PHÉP gộp bước liên quan (click ô + gõ, mở menu + chọn "
            "mục…) thành một bước logic, và BỎ bước dư (click nhầm, focus "
            "lặp, phím đặc biệt không cần thiết) để tài liệu gọn.")
        parts.append(
            "Mỗi bước ĐẦU RA gồm: 'source_indexes' (danh sách index gốc theo "
            "thứ tự được gộp), 'section', 'label', 'description'. Mỗi index "
            "gốc xuất hiện tối đa MỘT lần; bỏ bước = không đưa index đó vào "
            "bất kỳ source_indexes nào. Không tạo bước không có source_indexes.")
        schema = (
            '{"title": string, "summary": string, "steps": '
            '[{"source_indexes": [number], "section": string, '
            '"label": string, "description": string}]}')
    else:
        parts.append(
            "GIỮ NGUYÊN số bước và thứ tự (1:1): với MỖI bước đầu vào viết "
            "lại 'label', 'description' và 'section'; không gộp, không bỏ, "
            "giữ 'index'.")
        schema = (
            '{"title": string, "summary": string, "steps": '
            '[{"index": number, "section": string, "label": string, '
            '"description": string}]}')
    preset_ctx = PRESETS.get(cfg.preset, "")
    if preset_ctx:
        parts.append("MỤC ĐÍCH TÀI LIỆU:\n" + preset_ctx)
    if cfg.custom_prompt.strip():
        parts.append("YÊU CẦU THÊM TỪ NGƯỜI DÙNG:\n" + cfg.custom_prompt.strip())
    parts.append("Ngôn ngữ toàn bộ nội dung (title, summary, label, description): "
                 + (cfg.out_language or "Tiếng Việt") + ".")
    parts.append(
        "ĐỊNH DẠNG PHẢN HỒI: CHỈ trả về MỘT đối tượng JSON hợp lệ, không "
        "markdown, không giải thích ngoài JSON. Schema: " + schema)
    return "\n".join(parts)


def build_ai_messages(steps: List[Step], cfg: AppConfig) -> list:
    """Dựng danh sách messages theo chuẩn OpenAI chat.completions (vLLM tương thích)."""
    lines = [
        "Dưới đây là nhật ký thao tác thô cần biên soạn lại thành tài liệu.",
        "Mỗi dòng: index | thời điểm | hành động thô | cửa sổ đang active.",
        "Hãy suy ra quy trình nghiệp vụ và viết lại chuyên nghiệp.",
        "",
        "=== NHẬT KÝ THÔ ===",
    ]
    for s in steps:
        lines.append(
            f"[{s.index}] {s.timestamp} | {s.action} | cửa sổ: {s.window}")
        if s.description.strip():
            lines.append(f"    ghi chú hiện có: {s.description.strip()}")
    lines.append("=== HẾT NHẬT KÝ ===")
    lines.append("")
    lines.append(
        "Hãy biên soạn title, summary và danh sách steps theo đúng schema "
        "đã nêu trong system prompt.")
    text_block = "\n".join(lines)

    if cfg.use_vision:
        content = [{"type": "text", "text": text_block}]
        for s in steps:
            for b in s.images:
                content.append({"type": "text",
                                "text": f"[Ảnh minh hoạ bước index {s.index}]"})
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b}"},
                })
        user_content = content
    else:
        user_content = text_block

    return [
        {"role": "system", "content": _system_prompt(cfg)},
        {"role": "user", "content": user_content},
    ]


def _chat_completion(cfg: AppConfig, messages: list, use_response_format: bool) -> str:
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    # temperature thấp + max_tokens rộng: phù hợp biên soạn tài liệu qua vLLM
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    # vLLM thường chấp nhận key bất kỳ; vẫn gửi header cho endpoint tương thích OpenAI
    key = (cfg.api_key or "").strip() or "EMPTY"
    req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return obj["choices"][0]["message"]["content"]


def call_ai(cfg: AppConfig, steps: List[Step]) -> dict:
    """Gọi API (OpenAI / vLLM) và trả về dict {title, summary, steps:[...]}."""
    if not steps:
        raise RuntimeError("Không có bước nào để xử lý.")
    if not (cfg.base_url or "").strip():
        raise RuntimeError("Chưa cấu hình Base URL (endpoint) AI.")
    if not (cfg.model or "").strip():
        raise RuntimeError("Chưa cấu hình Model.")
    # API key có thể để trống với vLLM local; endpoint cloud vẫn nên có key
    messages = build_ai_messages(steps, cfg)
    try:
        content = _chat_completion(cfg, messages, True)
    except urllib.error.HTTPError as e:
        # vLLM / một số endpoint không hỗ trợ response_format -> thử lại.
        if e.code in (400, 404, 415, 422, 500, 501):
            try:
                content = _chat_completion(cfg, messages, False)
            except urllib.error.HTTPError as e2:
                body = e2.read().decode("utf-8", "replace")
                raise RuntimeError(f"Lỗi API {e2.code}: {body[:500]}")
            except urllib.error.URLError as e2:
                raise RuntimeError(f"Lỗi kết nối: {e2.reason}")
        else:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"Lỗi API {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Lỗi kết nối: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Lỗi khi gọi AI: {e}")
    return parse_ai_content(content)


def _strip_fences(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_one_step(s: dict, default_section: str = "") -> Optional[dict]:
    if not isinstance(s, dict):
        return None
    src = s.get("source_indexes")
    src_list = []
    if isinstance(src, list):
        src_list = [i for i in (_to_int(v) for v in src) if i is not None]
    section = (s.get("section") or s.get("part") or s.get("group")
               or default_section or "").strip()
    return {
        "index": _to_int(s.get("index")),
        "source_indexes": src_list,
        "section": section,
        "label": (s.get("label") or s.get("action") or "").strip(),
        "description": (s.get("description") or "").strip(),
    }


def _normalize_ai(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("JSON không đúng định dạng.")
    norm_steps = []
    # Ưu tiên steps phẳng; nếu AI trả sections[{title, steps}] thì bung ra
    raw_steps = obj.get("steps")
    if isinstance(raw_steps, list) and raw_steps:
        for s in raw_steps:
            n = _norm_one_step(s)
            if n:
                norm_steps.append(n)
    else:
        for sec in (obj.get("sections") or obj.get("parts") or []):
            if not isinstance(sec, dict):
                continue
            sec_title = (sec.get("title") or sec.get("section")
                         or sec.get("name") or "").strip()
            for s in (sec.get("steps") or []):
                n = _norm_one_step(s, default_section=sec_title)
                if n:
                    if not n["section"]:
                        n["section"] = sec_title
                    norm_steps.append(n)
    return {
        "title": (obj.get("title") or "").strip(),
        "summary": (obj.get("summary") or "").strip(),
        "steps": norm_steps,
    }


def parse_ai_content(text: str) -> dict:
    """Đọc JSON từ phản hồi AI một cách bền vững (chịu được ```fence``` và text thừa)."""
    raw = (text or "").strip()
    for cand in (raw, _strip_fences(raw)):
        try:
            return _normalize_ai(json.loads(cand))
        except Exception:
            pass
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        try:
            return _normalize_ai(json.loads(raw[start:end + 1]))
        except Exception:
            pass
    raise RuntimeError("Không đọc được JSON hợp lệ từ phản hồi AI.")


def apply_ai_result(recorder: "StepsRecorder", result: dict, merge: bool = False):
    """Gán kết quả AI vào recorder.

    merge=True: dựng lại danh sách bước theo 'source_indexes' (gộp/bỏ, giữ mọi ảnh
    của các bước nguồn). merge=False: chỉ cập nhật nhãn/mô tả theo 'index' (1:1).
    """
    if merge:
        old_by_index = {s.index: s for s in recorder.steps}
        rebuilt: List[Step] = []
        for d in result.get("steps", []):
            srcs = d.get("source_indexes") or ([d["index"]] if d.get("index") else [])
            src_steps = [old_by_index[i] for i in srcs if i in old_by_index]
            if not src_steps:
                continue
            base = src_steps[0]
            images: List[str] = []
            for s in src_steps:
                images.extend(s.images)
            rebuilt.append(Step(
                index=0,
                timestamp=base.timestamp,
                action=d.get("label") or base.action,
                window=base.window,
                description=d.get("description", ""),
                section=(d.get("section") or "").strip(),
                images=images,
            ))
        if rebuilt:                       # chỉ thay khi dựng lại hợp lệ (an toàn)
            recorder.steps = rebuilt
            recorder._renumber()
    else:
        by_index = {s["index"]: s for s in result.get("steps", []) if s.get("index") is not None}
        for step in recorder.steps:
            info = by_index.get(step.index)
            if info:
                if info.get("label"):
                    step.action = info["label"]
                if info.get("description"):
                    step.description = info["description"]
                if "section" in info:
                    step.section = (info.get("section") or "").strip()
    if result.get("title"):
        recorder.report_title = result["title"]
    if result.get("summary"):
        recorder.report_summary = result["summary"]


# --- Bộ máy ghi ---------------------------------------------------------------
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
        self.steps.clear()
        self.report_title = "Bản ghi các bước"
        self.report_summary = ""
        self.project_path = None
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

    def _grab_screen(self) -> Image.Image:
        if _HAS_MSS:
            with mss.mss() as sct:
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
                pass

    # ---- Xử lý sự kiện chuột ----
    def _on_click(self, x, y, button, pressed):
        if not self._recording or self._paused or not pressed:
            return
        self._flush_keys()  # đóng bước văn bản trước một cú click
        btn = {"Button.left": "trái", "Button.right": "phải",
               "Button.middle": "giữa"}.get(str(button), str(button))
        window = self._active_window_title()
        try:
            img = self._grab_screen()
            img = self._mark(img, x, y)
            b64 = self._to_b64(img)
        except Exception as e:
            b64 = None
            window += f"  [lỗi chụp màn hình: {e}]"
        action = f"Nhấp chuột {btn} tại ({x}, {y})"
        self._add_step(action, b64, window)

    # ---- Xử lý sự kiện bàn phím ----
    def _on_key(self, key):
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
                self._add_step(f'Nhập văn bản: "{text}"', None,
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

    # ---- Xuất báo cáo ----
    def export_html(self, path: str, title: Optional[str] = None,
                    include_toc: bool = True):
        title = title or self.report_title or "Bản ghi các bước"
        rows = []
        # Nhóm bước theo section (giữ thứ tự xuất hiện) cho mục lục lồng nhau
        section_order: List[str] = []
        section_steps: dict = {}  # section_key -> list[Step]
        has_any_section = any((s.section or "").strip() for s in self.steps)
        for s in self.steps:
            sec = (s.section or "").strip()
            if not sec and has_any_section:
                sec = "Các bước khác"
            key = sec or ""  # rỗng = không chia phần
            if key not in section_steps:
                section_steps[key] = []
                section_order.append(key)
            section_steps[key].append(s)

        prev_section = object()  # sentinel
        for s in self.steps:
            if s.images:
                imgs_html = (
                    '<figure class="shots">'
                    + "".join(
                        f'<img src="data:image/png;base64,{b}" '
                        f'alt="Minh họa bước {s.index}: {_esc(s.action)}">'
                        for b in s.images)
                    + "</figure>")
            else:
                imgs_html = ""
            if s.description:
                desc_body = "<br>".join(
                    _esc(line) if line.strip() else "<br>"
                    for line in s.description.splitlines())
                desc_html = f'<div class="desc">{desc_body}</div>'
            else:
                desc_html = ""
            win_html = (
                f'<p class="window">Ứng dụng / cửa sổ: <em>{_esc(s.window)}</em></p>'
                if s.window and s.window != "(không xác định)" else "")
            sec_name = (s.section or "").strip()
            if not sec_name and has_any_section:
                sec_name = "Các bước khác"
            heading_html = ""
            if sec_name and sec_name != prev_section:
                sec_idx = (section_order.index(sec_name) + 1
                           if sec_name in section_order else 0)
                heading_html = (
                    f'<header class="part-head" id="sec-{sec_idx}">'
                    f'<h2 class="part-title">{_esc(sec_name)}</h2></header>')
                prev_section = sec_name
            rows.append(f"""
            {heading_html}
            <section class="step" id="step-{s.index}" data-step="{s.index}"
                     data-section="{_esc(sec_name)}">
              <div class="head">
                <span class="badge">Bước {s.index}</span>
                <h2 class="action">{_esc(s.action)}</h2>
                <span class="time">{_esc(s.timestamp)}</span>
              </div>
              {desc_html}
              {win_html}
              {imgs_html}
            </section>""")

        # Mục lục: lồng bước trong từng phần (nếu có section)
        nav_blocks = []
        if has_any_section:
            for i, sec_key in enumerate(section_order, start=1):
                steps_in = section_steps[sec_key]
                children = "".join(
                    f'<li><a class="nav-link" href="#step-{st.index}" '
                    f'data-step="{st.index}">'
                    f'<span class="nav-n">{st.index}</span>'
                    f'<span class="nav-t">{_esc(st.action)}</span></a></li>'
                    for st in steps_in)
                nav_blocks.append(
                    f'<li class="nav-part">'
                    f'<a class="nav-part-link" href="#sec-{i}" data-step="sec-{i}">'
                    f'<span class="nav-part-t">Phần {i}: {_esc(sec_key)}</span></a>'
                    f'<ol class="nav-children">{children}</ol></li>')
        else:
            for s in self.steps:
                nav_blocks.append(
                    f'<li><a class="nav-link" href="#step-{s.index}" data-step="{s.index}">'
                    f'<span class="nav-n">{s.index}</span>'
                    f'<span class="nav-t">{_esc(s.action)}</span></a></li>')

        summary_html = ""
        summary_nav = ""
        if self.report_summary:
            sum_body = "<br>".join(
                _esc(line) if line.strip() else "<br>"
                for line in self.report_summary.splitlines())
            summary_html = (
                '<section class="summary" id="intro"><h2>Giới thiệu</h2>'
                f'<p>{sum_body}</p></section>'
            )
            summary_nav = (
                '<li><a class="nav-link" href="#intro" data-step="intro">'
                '<span class="nav-n">i</span>'
                '<span class="nav-t">Giới thiệu</span></a></li>')

        n_parts = len(section_order) if has_any_section else 0
        meta_parts = (
            f" · {n_parts} phần" if n_parts else "")
        sidebar_html = ""
        if include_toc and self.steps:
            sidebar_html = f"""
  <aside class="sidebar" id="sidebar" aria-label="Mục lục các bước">
    <div class="sidebar-head">
      <div class="sidebar-title">Mục lục</div>
      <div class="sidebar-meta">{len(self.steps)} bước{meta_parts}</div>
    </div>
    <nav class="side-nav">
      <ol>
        {summary_nav}
        {''.join(nav_blocks)}
      </ol>
    </nav>
  </aside>"""

        html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root {{
    --brand:#0b5cab; --brand-soft:#e8f1fb; --brand-active:#0a4d8c;
    --text:#1f2328; --muted:#57606a; --line:#d0d7de; --bg:#f6f8fa;
    --card:#fff; --sidebar-w:280px;
  }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{ font-family:"Segoe UI", system-ui, -apple-system, sans-serif; margin:0;
         background:var(--bg); color:var(--text); line-height:1.55; }}
  .topbar {{ background:linear-gradient(135deg,#0b5cab 0%,#1f6feb 100%);
             color:#fff; padding:20px 28px; position:sticky; top:0; z-index:20;
             box-shadow:0 1px 0 rgba(0,0,0,.08); }}
  .topbar .doc-type {{ display:inline-block; font-size:11px; letter-spacing:.06em;
                       text-transform:uppercase; opacity:.9; margin-bottom:6px;
                       border:1px solid rgba(255,255,255,.35); border-radius:999px;
                       padding:2px 10px; }}
  .topbar h1 {{ margin:0; font-size:22px; font-weight:700; line-height:1.3; }}
  .topbar .meta {{ margin:8px 0 0; opacity:.88; font-size:13px; }}
  .layout {{ display:flex; align-items:flex-start; min-height:calc(100vh - 110px); }}
  .sidebar {{
    position:sticky; top:110px; align-self:flex-start;
    width:var(--sidebar-w); flex:0 0 var(--sidebar-w);
    height:calc(100vh - 110px); overflow:auto;
    background:#fff; border-right:1px solid var(--line);
    padding:0 0 24px;
  }}
  .sidebar-head {{ padding:16px 16px 10px; border-bottom:1px solid var(--line);
                   position:sticky; top:0; background:#fff; z-index:1; }}
  .sidebar-title {{ font-size:12px; font-weight:700; color:var(--brand);
                    text-transform:uppercase; letter-spacing:.05em; }}
  .sidebar-meta {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .side-nav ol {{ list-style:none; margin:8px 0 0; padding:0 8px; }}
  .side-nav li {{ margin:2px 0; }}
  .nav-link, .nav-part-link {{
    display:flex; gap:10px; align-items:flex-start;
    text-decoration:none; color:var(--text); padding:8px 10px;
    border-radius:8px; font-size:13px; line-height:1.35;
    border-left:3px solid transparent;
  }}
  .nav-link:hover, .nav-part-link:hover {{ background:var(--brand-soft); color:var(--brand); }}
  .nav-link.active, .nav-part-link.active {{
    background:var(--brand-soft); color:var(--brand-active);
    border-left-color:var(--brand); font-weight:600;
  }}
  .nav-n, .nav-part-n {{
    flex:0 0 1.6em; min-width:1.6em; height:1.6em; line-height:1.6em;
    text-align:center; font-size:11px; font-weight:700;
    background:#eef2f6; color:var(--muted); border-radius:999px;
  }}
  .nav-link.active .nav-n, .nav-part-link.active .nav-part-n {{
    background:var(--brand); color:#fff;
  }}
  .nav-t, .nav-part-t {{ flex:1; word-break:break-word; }}
  .nav-part {{ margin:8px 0 4px; }}
  .nav-part-link {{
    font-weight:700; font-size:12.5px; color:var(--brand-active);
    text-transform:none; padding:7px 10px 5px;
  }}
  .nav-part-n {{
    background:var(--brand-soft); color:var(--brand);
  }}
  .nav-children {{
    list-style:none; margin:2px 0 6px 0; padding:0 0 0 6px;
    border-left:2px solid #e8eef5;
  }}
  .nav-children .nav-link {{ padding:6px 8px 6px 10px; font-size:12.5px; }}
  .content {{ flex:1; min-width:0; max-width:920px; padding:24px 22px 48px; }}
  .summary, .step {{
    background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:18px 22px; margin-bottom:20px;
  }}
  .summary {{ border-left:5px solid var(--brand); }}
  .summary h2 {{ margin:0 0 10px; font-size:15px; color:var(--brand);
                 text-transform:uppercase; letter-spacing:.04em; }}
  .summary p {{ margin:0; color:#24292f; }}
  .part-head {{
    margin:28px 0 14px; padding:0 2px 10px;
    border-bottom:2px solid var(--brand);
    scroll-margin-top:120px;
  }}
  .part-head:first-child {{ margin-top:4px; }}
  .part-title {{
    margin:0; font-size:17px; font-weight:700; color:var(--brand-active);
    letter-spacing:.01em;
  }}
  .step {{ scroll-margin-top:128px; }}
  .head {{ display:grid; grid-template-columns:auto 1fr auto; gap:10px 14px;
           align-items:start; border-bottom:1px solid #eaeef2;
           padding-bottom:12px; margin-bottom:12px; }}
  .badge {{ display:inline-block; background:var(--brand-soft); color:var(--brand);
            font-weight:700; font-size:12px; padding:4px 10px; border-radius:999px;
            white-space:nowrap; margin-top:2px; }}
  .action {{ margin:0; font-size:18px; font-weight:650; line-height:1.35;
             color:#0d1117; grid-column:2; }}
  .time {{ font-size:12px; color:var(--muted); white-space:nowrap; margin-top:4px; }}
  .desc {{ font-size:15px; margin:0 0 10px; color:#24292f; }}
  .window {{ font-size:12px; color:var(--muted); margin:0 0 10px; }}
  .shots {{ margin:12px 0 0; padding:0; }}
  .shots img {{ max-width:100%; border:1px solid var(--line); border-radius:8px;
                display:block; margin-top:10px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
  footer {{ max-width:920px; padding:0 22px 36px; font-size:12px;
            color:var(--muted); text-align:center; }}
  .menu-toggle {{
    display:none; position:fixed; bottom:18px; left:18px; z-index:30;
    background:var(--brand); color:#fff; border:0; border-radius:999px;
    padding:10px 16px; font-size:13px; font-weight:600; cursor:pointer;
    box-shadow:0 4px 14px rgba(11,92,171,.35);
  }}
  @media (max-width:900px) {{
    .layout {{ display:block; }}
    .sidebar {{
      position:fixed; left:0; top:0; bottom:0; z-index:40;
      width:min(86vw, 300px); height:100vh; transform:translateX(-105%);
      transition:transform .2s ease; box-shadow:4px 0 20px rgba(0,0,0,.12);
    }}
    body.nav-open .sidebar {{ transform:translateX(0); }}
    .menu-toggle {{ display:inline-flex; align-items:center; gap:6px; }}
    .content {{ max-width:none; padding:18px 14px 72px; }}
    .step {{ scroll-margin-top:100px; }}
  }}
  @media print {{
    body {{ background:#fff; }}
    .topbar {{ position:static; background:#0b5cab !important;
               -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .sidebar, .menu-toggle {{ display:none !important; }}
    .layout {{ display:block; }}
    .content {{ max-width:none; padding:12px 0; }}
    .step, .summary {{ break-inside:avoid; box-shadow:none; }}
  }}
</style></head>
<body>
  <header class="topbar">
    <div class="doc-type">Hướng dẫn sử dụng</div>
    <h1>{_esc(title)}</h1>
    <p class="meta">Ban hành: {self._now()} · Tổng số bước: {len(self.steps)}</p>
  </header>
  <div class="layout">
    {sidebar_html}
    <div class="content">
      {summary_html}
      {''.join(rows)}
      <footer>Tài liệu được biên soạn từ bản ghi thao tác · {len(self.steps)} bước</footer>
    </div>
  </div>
  <button type="button" class="menu-toggle" id="menuToggle" aria-label="Mở mục lục">☰ Mục lục</button>
<script>
(function () {{
  var links = Array.prototype.slice.call(
    document.querySelectorAll(".nav-link, .nav-part-link"));
  var sections = Array.prototype.slice.call(
    document.querySelectorAll(".step, .summary, .part-head"));
  var body = document.body;
  var btn = document.getElementById("menuToggle");
  var sidebar = document.getElementById("sidebar");

  function setActive(id) {{
    links.forEach(function (a) {{
      var href = a.getAttribute("href") || "";
      a.classList.toggle("active", href === "#" + id);
    }});
  }}

  links.forEach(function (a) {{
    a.addEventListener("click", function () {{
      body.classList.remove("nav-open");
      var href = a.getAttribute("href") || "";
      if (href.charAt(0) === "#") setActive(href.slice(1));
    }});
  }});

  if (btn) {{
    btn.addEventListener("click", function () {{
      body.classList.toggle("nav-open");
    }});
  }}
  document.addEventListener("click", function (e) {{
    if (!body.classList.contains("nav-open")) return;
    if (sidebar && sidebar.contains(e.target)) return;
    if (btn && btn.contains(e.target)) return;
    body.classList.remove("nav-open");
  }});

  if ("IntersectionObserver" in window && sections.length) {{
    var io = new IntersectionObserver(function (entries) {{
      var visible = entries
        .filter(function (en) {{ return en.isIntersecting; }})
        .sort(function (a, b) {{ return b.intersectionRatio - a.intersectionRatio; }});
      if (visible[0] && visible[0].target && visible[0].target.id) {{
        setActive(visible[0].target.id);
        var act = document.querySelector(".nav-link.active");
        if (act && sidebar) {{
          var r = act.getBoundingClientRect();
          var sr = sidebar.getBoundingClientRect();
          if (r.top < sr.top + 40 || r.bottom > sr.bottom - 20) {{
            act.scrollIntoView({{ block: "nearest" }});
          }}
        }}
      }}
    }}, {{ rootMargin: "-30% 0px -55% 0px", threshold: [0.1, 0.4, 0.7] }});
    sections.forEach(function (s) {{ io.observe(s); }});
  }}
  if (location.hash) setActive(location.hash.slice(1));
  else if (document.getElementById("intro")) setActive("intro");
  else if (sections[0]) setActive(sections[0].id);
}})();
</script>
</body></html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


# --- Theme giao diện ----------------------------------------------------------
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


# --- Hộp thoại Cấu hình (AI) -------------------------------------------------
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
        self.config_obj.save()
        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Cấu hình", "Đã lưu cấu hình.", parent=self)
        self.destroy()


# --- Xem ảnh phóng to (cuộn + zoom) ------------------------------------------
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


# --- Cửa sổ Xem lại & Chỉnh sửa ----------------------------------------------
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
        _btn(right_bar, "⚙ Cấu hình", command=self.on_settings, variant="ghost").pack(
            side="left", padx=2)
        self.btn_undo = _btn(right_bar, "↩ Hoàn tác AI", command=self._undo_ai,
                             variant="ghost", state="disabled")
        self.btn_undo.pack(side="left", padx=2)
        self.btn_ai = _btn(right_bar, "✨ AI biên soạn HDSD", command=self._run_ai,
                           variant="accent")
        self.btn_ai.pack(side="left", padx=(6, 0))

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
        self.btn_ai.config(state="disabled" if busy else "normal")

    def _run_ai(self):
        self._sync_to_steps()
        cfg = self.config_obj
        if not (cfg.base_url or "").strip() or not (cfg.model or "").strip():
            messagebox.showwarning(
                "AI",
                "Chưa cấu hình Base URL / Model.\n"
                "Mở ⚙ Cấu hình (vLLM: http://host:8000/v1 + tên model).",
                parent=self)
            return
        if self.rec.step_count == 0:
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


# --- Giao diện điều khiển (tkinter) ------------------------------------------
class RecorderGUI:
    def __init__(self):
        self.config = AppConfig.load()
        self.rec = StepsRecorder()
        self.rec.on_step_added = self._on_step_added

        self.root = tk.Tk()
        self.root.title("Steps Recorder")
        self.root.geometry("420x400")
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

        tip = tk.Label(
            body,
            text="Mẹo: cửa sổ luôn nổi trên cùng khi ghi. Dừng để chỉnh sửa & xuất.",
            bg=UITheme.BG, fg=UITheme.MUTED, font=_ui_font(UITheme.FONT_SMALL),
            wraplength=380, justify="left",
        )
        tip.pack(fill="x", pady=(14, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
            self.config.save()
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
        self.count.set(str(step.index))

    def _on_close(self):
        if self.rec.is_recording:
            self.rec.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    RecorderGUI().run()
