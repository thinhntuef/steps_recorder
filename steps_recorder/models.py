"""Cấu trúc dữ liệu một bước và hằng số định dạng dự án."""
from dataclasses import dataclass, field
from typing import List


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
