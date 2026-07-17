# Steps Recorder

Công cụ Python ghi lại thao tác người dùng (click chuột, phím gõ) kèm ảnh chụp màn hình, tương tự "Steps Recorder / Problem Steps Recorder (PSR)" của Windows — có bổ sung khả năng dùng AI để biên soạn lại thành tài liệu hướng dẫn sử dụng chuyên nghiệp.

## Tính năng

- Ghi lại click chuột và phím gõ, chụp màn hình khoanh tròn vị trí con trỏ.
- Gộp các phím gõ liên tiếp thành một bước "Nhập văn bản".
- Cửa sổ xem lại & chỉnh sửa sau khi ghi: xoá bước, xoá bớt ảnh, sửa nhãn/mô tả, sửa tiêu đề/tóm tắt trước khi xuất.
- Trợ lý AI (tương thích OpenAI API / vLLM): biên soạn lại nhật ký thô thành hướng dẫn sử dụng (nhãn, mô tả, tiêu đề, tóm tắt), tự động chia phần mục lục, có thể gộp/bỏ bước dư thừa.
- Xuất báo cáo HTML tự chứa (ảnh nhúng base64), có mục lục theo phần và bước.
- Lưu / mở lại dự án (`.steps.json`) để tiếp tục chỉnh sửa sau.

## Cài đặt

Yêu cầu Python 3. Cài các thư viện phụ thuộc:

```bash
pip install pynput pillow mss pygetwindow
```

Tính năng AI gọi API qua `urllib` (thư viện chuẩn Python) nên không cần cài thêm gì.

## Sử dụng

```bash
python steps_recorder.py
```

Trong cửa sổ chính, bấm nút **⚙ Cấu hình** để thiết lập kết nối AI (base URL, model, API key, mục đích tài liệu, ngôn ngữ đầu ra...).

## Lưu ý

- Cấu hình ứng dụng (bao gồm API key) được lưu tại `~/.steps_recorder_config.json` dưới dạng plaintext — không commit file này lên git (đã được loại trừ trong `.gitignore`).
- Dự án đã lưu (`*.steps.json`) và báo cáo xuất ra (`*.html`) cũng được loại trừ khỏi git theo mặc định.
