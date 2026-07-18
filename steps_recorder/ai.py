"""Tầng AI (hàm thuần, tách khỏi GUI để dễ kiểm thử).

Gọi API chat-completions tương thích OpenAI/vLLM qua urllib, phân tích JSON
trả về một cách bền vững và áp kết quả vào StepsRecorder.
"""
import json
import logging
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, List, Optional

from .config import AppConfig, PRESETS
from .models import Step

if TYPE_CHECKING:
    from .recorder import StepsRecorder

log = logging.getLogger("steps_recorder")


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

    user_content: object
    if cfg.use_vision:
        content: List[dict] = [{"type": "text", "text": text_block}]
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

