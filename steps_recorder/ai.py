"""Tầng AI (hàm thuần, tách khỏi GUI để dễ kiểm thử).

Gọi API chat-completions tương thích OpenAI/vLLM qua urllib, phân tích JSON
trả về một cách bền vững và áp kết quả vào StepsRecorder.
"""
import json
import re
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


def _request_timeout(cfg: AppConfig) -> int:
    try:
        t = int(cfg.request_timeout)
    except (TypeError, ValueError):
        t = 600
    return max(30, t)


def _chat_completion_meta(cfg: AppConfig, messages: list, use_response_format: bool,
                          max_tokens: int = 4096) -> tuple:
    """Gọi API, trả về (nội dung, finish_reason).

    finish_reason == "length" nghĩa là phản hồi bị cắt vì chạm max_tokens —
    tín hiệu để vòng lặp tiếp nối yêu cầu AI viết tiếp.
    """
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    # temperature thấp + max_tokens rộng: phù hợp biên soạn tài liệu qua vLLM
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    # vLLM thường chấp nhận key bất kỳ; vẫn gửi header cho endpoint tương thích OpenAI
    key = (cfg.api_key or "").strip() or "EMPTY"
    req.add_header("Authorization", f"Bearer {key}")
    timeout = _request_timeout(cfg)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except TimeoutError:
        raise RuntimeError(
            f"Hết thời gian chờ AI ({timeout}s). Tăng 'Timeout (giây)' trong "
            "⚙ Cấu hình, hoặc dùng model nhanh hơn / tắt gửi ảnh (vision).")
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), TimeoutError):
            raise RuntimeError(
                f"Hết thời gian chờ AI ({timeout}s). Tăng 'Timeout (giây)' trong "
                "⚙ Cấu hình, hoặc dùng model nhanh hơn / tắt gửi ảnh (vision).")
        raise
    obj = json.loads(raw)
    choice = obj["choices"][0]
    return choice["message"]["content"], (choice.get("finish_reason") or "")


def _chat_completion(cfg: AppConfig, messages: list, use_response_format: bool,
                     max_tokens: int = 4096) -> str:
    return _chat_completion_meta(cfg, messages, use_response_format,
                                 max_tokens=max_tokens)[0]


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



# --- AI tạo HTML trực quan ----------------------------------------------------
# AI tự thiết kế toàn bộ file HTML (bố cục, CSS) thay vì dùng template cố định.
# Ảnh không đi qua AI: AI chèn placeholder {{IMG_<bước>_<số ảnh>}}, ứng dụng
# thay bằng ảnh base64 thật sau khi nhận HTML (render_ai_html).
IMG_PLACEHOLDER_RE = re.compile(r"\{\{\s*IMG_(\d+)_(\d+)\s*\}\}")


def _html_system_prompt(cfg: AppConfig) -> str:
    preset_ctx = PRESETS.get(cfg.preset, "")
    extra = (cfg.custom_prompt or "").strip()
    parts = [
        "Bạn là chuyên gia thiết kế tài liệu web. Nhiệm vụ: từ nhật ký thao tác "
        "thô (danh sách bước + ảnh chụp màn hình), tạo MỘT file HTML hoàn chỉnh, "
        "TỰ CHỨA, trình bày đẹp, hiện đại, dễ đọc.",
        f"Ngôn ngữ nội dung: {cfg.out_language}.",
        f"Bối cảnh tài liệu: {preset_ctx}" if preset_ctx else "",
        f"Yêu cầu thêm từ người dùng: {extra}" if extra else "",
        "",
        "YÊU CẦU BẮT BUỘC:",
        "- Trả về DUY NHẤT mã HTML (bắt đầu bằng <!DOCTYPE html>), không giải thích gì thêm.",
        "- Toàn bộ CSS đặt trong một thẻ <style> nội tuyến. KHÔNG tải tài nguyên "
        "ngoài (font, CDN, ảnh mạng), KHÔNG dùng JavaScript ngoài; JS nội tuyến "
        "nhỏ (mục lục, cuộn) được phép.",
        "- Viết lại các bước thành hướng dẫn rõ ràng: nhóm thành các phần hợp lý, "
        "đặt tiêu đề tài liệu, đoạn tóm tắt mở đầu, mục lục liên kết tới từng phần.",
        "- Gộp/bỏ bước trùng lặp, vô nghĩa; che thông tin nhạy cảm nếu thấy.",
        "- VỊ TRÍ ẢNH: với mỗi ảnh minh hoạ, chèn đúng chuỗi placeholder dạng "
        "{{IMG_3_1}} (ảnh 1 của bước gốc số 3) trên một dòng riêng tại vị trí phù "
        "hợp. TUYỆT ĐỐI KHÔNG tự viết thẻ <img>, KHÔNG viết dữ liệu base64. "
        "Chỉ dùng các placeholder có trong danh sách được cung cấp, mỗi cái một lần.",
        "- Thiết kế: khoảng trắng thoáng, chữ dễ đọc, bước được đánh số nổi bật, "
        "ảnh có khung/bo góc, in ấn tốt (print-friendly).",
    ]
    return "\n".join(p for p in parts if p)


def build_html_messages(steps: List[Step], cfg: AppConfig,
                        title: str = "", summary: str = "") -> list:
    lines = ["=== NHẬT KÝ THÔ ==="]
    if (title or "").strip():
        lines.insert(0, f"Tiêu đề hiện có: {title.strip()}")
    if (summary or "").strip():
        lines.insert(1 if lines[0].startswith("Tiêu đề") else 0,
                     f"Tóm tắt hiện có: {summary.strip()}")
    placeholders = []
    for s in steps:
        lines.append(f"[{s.index}] {s.timestamp} | {s.action} | cửa sổ: {s.window}")
        if s.description.strip():
            lines.append(f"    ghi chú hiện có: {s.description.strip()}")
        for j in range(1, len(s.images) + 1):
            placeholders.append(f"{{{{IMG_{s.index}_{j}}}}}")
    lines.append("=== HẾT NHẬT KÝ ===")
    lines.append("")
    if placeholders:
        lines.append("Danh sách placeholder ảnh được phép dùng (mỗi cái một lần): "
                     + ", ".join(placeholders))
    else:
        lines.append("Không có ảnh minh hoạ nào — không chèn placeholder.")
    lines.append("Hãy tạo file HTML hoàn chỉnh theo yêu cầu trong system prompt.")
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
        {"role": "system", "content": _html_system_prompt(cfg)},
        {"role": "user", "content": user_content},
    ]


def extract_html(text: str) -> str:
    """Lấy tài liệu HTML từ phản hồi AI (chịu được ```fence``` và text thừa)."""
    t = _strip_fences((text or "").strip())
    low = t.lower()
    for marker in ("<!doctype", "<html"):
        pos = low.find(marker)
        if pos != -1:
            if pos > 0:
                t = t[pos:]
                low = t.lower()
            break
    if "<html" not in low and "<!doctype" not in low:
        raise RuntimeError("Phản hồi AI không chứa tài liệu HTML hợp lệ.")
    # cắt phần thừa sau </html> nếu có
    end = low.rfind("</html>")
    if end != -1:
        t = t[:end + len("</html>")]
    return t


def render_ai_html(html: str, steps: List[Step]) -> str:
    """Thay placeholder {{IMG_i_j}} bằng ảnh base64 thật.

    Ảnh không được AI đặt vào đâu sẽ gom vào "Phụ lục ảnh" cuối trang để
    không mất dữ liệu.
    """
    imgs = {}
    for s in steps:
        for j, b in enumerate(s.images, start=1):
            imgs[(s.index, j)] = b
    used = set()

    def _sub(m):
        key = (int(m.group(1)), int(m.group(2)))
        b64 = imgs.get(key)
        if b64 is None:
            return ""  # placeholder AI bịa ra -> bỏ
        used.add(key)
        return (f'<img src="data:image/png;base64,{b64}" '
                f'alt="Minh hoạ bước {key[0]}" '
                'style="max-width:100%;height:auto;border-radius:8px;'
                'box-shadow:0 2px 14px rgba(0,0,0,.18);margin:10px 0">')

    out = IMG_PLACEHOLDER_RE.sub(_sub, html)

    unused = sorted(k for k in imgs if k not in used)
    if unused:
        parts = ['<section style="max-width:960px;margin:40px auto;padding:0 16px">',
                 '<h2>Phụ lục ảnh</h2>']
        for (i, j) in unused:
            parts.append(
                '<figure style="margin:16px 0">'
                f'<img src="data:image/png;base64,{imgs[(i, j)]}" '
                f'alt="Bước {i}" style="max-width:100%;height:auto;'
                'border-radius:8px;box-shadow:0 2px 14px rgba(0,0,0,.18)">'
                f'<figcaption>Bước {i} · ảnh {j}</figcaption></figure>')
        parts.append("</section>")
        block = "\n".join(parts)
        if "</body>" in out:
            out = out.replace("</body>", block + "\n</body>", 1)
        else:
            out += "\n" + block
    return out


# Vòng lặp tiếp nối (agentic loop): một request thường KHÔNG đủ token để AI
# viết xong cả trang HTML. Sau mỗi lượt, nếu phản hồi bị cắt (finish_reason
# "length") hoặc tài liệu chưa đóng </html>, gửi tiếp yêu cầu "viết tiếp từ
# chỗ dừng" kèm phần đã viết làm ngữ cảnh — lặp tới khi hoàn chỉnh.
MAX_HTML_ROUNDS = 6

_CONTINUE_PROMPT = (
    "Phần HTML trên bị dừng giữa chừng. Hãy VIẾT TIẾP CHÍNH XÁC từ ký tự "
    "cuối cùng ở trên: không lặp lại phần đã viết, không mở đầu bằng lời dẫn, "
    "không dùng code fence, không bắt đầu lại tài liệu. Kết thúc bằng </html> "
    "khi đã xong.")


def merge_continuation(prev: str, nxt: str, min_overlap: int = 16,
                       max_overlap: int = 400) -> str:
    """Cắt đoạn trùng ở mối nối khi model lặp lại đuôi phần trước.

    Trả về phần cần nối thêm vào prev. Chỉ cắt khi đoạn trùng đủ dài
    (>= min_overlap) để không cắt nhầm trùng hợp ngẫu nhiên vài ký tự.
    """
    nxt = _strip_fences(nxt)
    limit = min(len(prev), len(nxt), max_overlap)
    for k in range(limit, min_overlap - 1, -1):
        if prev.endswith(nxt[:k]):
            return nxt[k:]
    return nxt


def call_ai_html(cfg: AppConfig, steps: List[Step],
                 title: str = "", summary: str = "",
                 on_progress=None) -> str:
    """Gọi AI tạo HTML trực quan (nhiều lượt nếu cần); trả về HTML đã gắn ảnh.

    on_progress(round_no, max_rounds): callback tiến độ vòng lặp (chạy trên
    luồng worker — bên GUI tự marshal về luồng Tk).
    """
    if not steps:
        raise RuntimeError("Không có bước nào để xử lý.")
    if not (cfg.base_url or "").strip():
        raise RuntimeError("Chưa cấu hình Base URL (endpoint) AI.")
    if not (cfg.model or "").strip():
        raise RuntimeError("Chưa cấu hình Model.")
    messages = build_html_messages(steps, cfg, title=title, summary=summary)
    html = ""
    try:
        for round_no in range(1, MAX_HTML_ROUNDS + 1):
            if on_progress:
                try:
                    on_progress(round_no, MAX_HTML_ROUNDS)
                except Exception:
                    pass
            content, finish = _chat_completion_meta(
                cfg, messages, use_response_format=False, max_tokens=8192)
            if html:
                html += merge_continuation(html, content)
            else:
                html = _strip_fences(content)
            if finish != "length" and "</html>" in html.lower():
                break
            log.info("AI HTML vòng %s/%s: chưa hoàn chỉnh (finish=%s), tiếp tục",
                     round_no, MAX_HTML_ROUNDS, finish or "?")
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": _CONTINUE_PROMPT})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Lỗi API {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Lỗi kết nối: {e.reason}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Lỗi khi gọi AI: {e}")
    if "</html>" not in html.lower():
        # hết vòng mà vẫn chưa đóng tài liệu -> tự vá để không mất phần đã có
        log.warning("AI HTML: hết %s vòng vẫn chưa có </html>, tự đóng tài liệu",
                    MAX_HTML_ROUNDS)
        html += "\n</body></html>"
    return render_ai_html(extract_html(html), steps)
