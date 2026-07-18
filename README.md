# Steps Recorder

Công cụ Python ghi lại thao tác người dùng (click chuột, phím gõ) kèm ảnh chụp màn hình, tương tự "Steps Recorder / Problem Steps Recorder (PSR)" của Windows — có bổ sung khả năng dùng AI để biên soạn lại thành tài liệu hướng dẫn sử dụng chuyên nghiệp.

## Tính năng

- Ghi lại click chuột và phím gõ, chụp màn hình khoanh tròn vị trí con trỏ (chọn đúng màn hình chứa điểm click trên hệ thống nhiều màn hình).
- Nhận diện nhấp đúp chuột (hai click cùng nút trong 0,4 giây) thành một bước "Nhấp đúp chuột".
- Gộp các phím gõ liên tiếp thành một bước "Nhập văn bản".
- **Chế độ riêng tư (mặc định BẬT)**: che nội dung gõ phím — mật khẩu và dữ liệu nhạy cảm không đi vào file dự án, báo cáo hay tin nhắn gửi AI. Tắt/bật bằng checkbox 🔒 ở cửa sổ chính.
- Phím tắt toàn cục: **F9** Ghi / Tạm dừng / Tiếp tục, **F10** Dừng & sửa (không khả dụng trên Wayland; phím tắt không bị ghi thành bước).
- Cửa sổ xem lại & chỉnh sửa sau khi ghi: xoá bước, xoá bớt ảnh, sửa nhãn/mô tả, sửa tiêu đề/tóm tắt trước khi xuất.
- Trợ lý AI (tương thích OpenAI API / vLLM): biên soạn lại nhật ký thô thành hướng dẫn sử dụng (nhãn, mô tả, tiêu đề, tóm tắt), tự động chia phần mục lục, có thể gộp/bỏ bước dư thừa.
- Xuất báo cáo HTML tự chứa (ảnh nhúng base64), có mục lục theo phần và bước.
- Xuất Markdown (`.md`) kèm thư mục ảnh `*_assets` — hiển thị được trên GitHub / VS Code; khi chia sẻ hãy gửi kèm thư mục ảnh.
- Lưu / mở lại dự án (`.steps.json`) để tiếp tục chỉnh sửa sau.

## Cài đặt

Yêu cầu Python 3. Cài các thư viện phụ thuộc:

```bash
pip install -r requirements.txt
```

Tính năng AI gọi API qua `urllib` (thư viện chuẩn Python) nên không cần cài thêm gì.

## Sử dụng

```bash
python steps_recorder.py
```

Trong cửa sổ chính, bấm nút **⚙ Cấu hình** để thiết lập kết nối AI (base URL, model, API key, mục đích tài liệu, ngôn ngữ đầu ra...).

Phím tắt khi ghi: **F9** bắt đầu / tạm dừng / tiếp tục, **F10** dừng và mở cửa sổ chỉnh sửa. Lưu ý phím tắt chỉ được "lắng nghe" chứ không bị chặn — ứng dụng đang có tiêu điểm vẫn nhận được phím F9/F10.

## Kiểm thử

```bash
pip install pytest
python -m pytest tests/
```

## Lưu ý

- Cấu hình ứng dụng (bao gồm API key) được lưu tại `~/.steps_recorder_config.json` dưới dạng plaintext (file được tạo với quyền `0600` — chỉ chủ sở hữu đọc/ghi) — không commit file này lên git (đã được loại trừ trong `.gitignore`).
- Chế độ riêng tư chỉ che nội dung **gõ phím**; ảnh chụp màn hình vẫn có thể chứa dữ liệu nhạy cảm hiển thị trên màn hình — hãy xoá/kiểm tra ảnh trong cửa sổ chỉnh sửa trước khi chia sẻ.
- Dự án đã lưu (`*.steps.json`) và báo cáo xuất ra (`*.html`) cũng được loại trừ khỏi git theo mặc định.
