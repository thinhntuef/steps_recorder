import base64
import io

import pytest
from PIL import Image

from steps_recorder import Step, StepsRecorder

docx = pytest.importorskip("docx")


def _tiny_png_b64(size=(4, 4)):
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 128, 255)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _recorder():
    rec = StepsRecorder()
    rec.report_title = "Hướng dẫn thử DOCX"
    rec.report_summary = "Tóm tắt."
    rec.steps = [
        Step(index=1, timestamp="t1", action="Mở ứng dụng", window="App",
             description="Chi tiết", section="Phần 1",
             images=[_tiny_png_b64()]),
        Step(index=2, timestamp="t2", action="Nhấn nút", window="(không xác định)",
             section="Phần 2", images=[_tiny_png_b64((800, 400))]),
    ]
    return rec


def test_export_docx_structure(tmp_path):
    out = _recorder().export_docx(str(tmp_path / "guide.docx"))
    doc = docx.Document(out)
    texts = [p.text for p in doc.paragraphs]
    assert "Hướng dẫn thử DOCX" in texts
    assert "Phần 1" in texts
    assert "Bước 1: Mở ứng dụng" in texts
    assert any("Ứng dụng / cửa sổ: App" in t for t in texts)
    # cửa sổ "(không xác định)" không được in
    assert not any("(không xác định)" in t for t in texts)
    assert len(doc.inline_shapes) == 2  # cả 2 ảnh được nhúng


def test_export_docx_appends_extension(tmp_path):
    out = _recorder().export_docx(str(tmp_path / "guide"))
    assert out.endswith(".docx")
    docx.Document(out)  # mở được
