"""Cấu hình ứng dụng (AppConfig) và các preset mục đích tài liệu."""
import json
import logging
import os
from dataclasses import asdict, dataclass

log = logging.getLogger("steps_recorder")

CONFIG_FILETYPES = [
    ("Cấu hình Steps Recorder", "*.config.json"),
    ("JSON", "*.json"),
    ("Tất cả", "*.*"),
]


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
    mask_typed_text: bool = True      # che nội dung gõ phím (mật khẩu…)
    preset: str = "Hướng dẫn sử dụng"
    custom_prompt: str = ""
    out_language: str = "Tiếng Việt"
    ai_merge_steps: bool = True       # cho AI gộp/bỏ bước
    export_toc: bool = True           # xuất HTML kèm mục lục
    auto_process: bool = False        # dừng ghi là AI tự biên soạn & xuất HTML

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
        except FileNotFoundError:
            return cls()  # lần chạy đầu — chưa có file, không cần báo
        except Exception as e:
            log.warning("File cấu hình hỏng, dùng mặc định (%s): %s",
                        CONFIG_PATH, e)
            return cls()

    def save(self) -> bool:
        """Lưu cấu hình. Trả về False khi thất bại để nơi gọi cảnh báo."""
        try:
            # Tạo file với quyền 0600 (chỉ chủ sở hữu đọc/ghi) vì có api_key.
            fd = os.open(CONFIG_PATH,
                         os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(include_api_key=True), f,
                          ensure_ascii=False, indent=2)
            try:
                os.chmod(CONFIG_PATH, 0o600)  # siết lại file có sẵn từ bản cũ
            except OSError:
                pass
            return True
        except Exception:
            log.exception("Không lưu được cấu hình %s", CONFIG_PATH)
            return False

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

