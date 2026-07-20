# Steps Recorder

Công cụ Python ghi lại thao tác người dùng (click chuột, phím gõ) kèm ảnh chụp màn hình, tương tự "Steps Recorder / Problem Steps Recorder (PSR)" của Windows — có bổ sung khả năng dùng AI để biên soạn lại thành tài liệu hướng dẫn sử dụng chuyên nghiệp.

## Tính năng

- Ghi lại click chuột và phím gõ, chụp màn hình khoanh tròn vị trí con trỏ (chọn đúng màn hình chứa điểm click trên hệ thống nhiều màn hình; tự bật DPI awareness trên Windows để toạ độ không lệch khi màn hình scale 125%/150%).
- Nhận diện phần tử UI được click trên Windows (qua UI Automation / pywinauto): nhãn bước thành "Nhấp chuột trái vào nút 'Đăng nhập'" thay vì chỉ toạ độ. Thiếu pywinauto hoặc chạy trên hệ khác thì tự động bỏ qua.
- Nhận diện nhấp đúp chuột (hai click cùng nút trong 0,4 giây) thành một bước "Nhấp đúp chuột".
- Gộp các phím gõ liên tiếp thành một bước "Nhập văn bản".
- **Chế độ riêng tư (mặc định BẬT)**: che nội dung gõ phím — mật khẩu và dữ liệu nhạy cảm không đi vào file dự án, báo cáo hay tin nhắn gửi AI. Tắt/bật bằng checkbox 🔒 ở cửa sổ chính.
- Phím tắt toàn cục: **F9** Ghi / Tạm dừng / Tiếp tục, **F10** Dừng & sửa (không khả dụng trên Wayland; phím tắt không bị ghi thành bước).
- Cửa sổ xem lại & chỉnh sửa sau khi ghi: xoá bước, xoá bớt ảnh, sửa nhãn/mô tả, sửa tiêu đề/tóm tắt trước khi xuất.
- Trợ lý AI (tương thích OpenAI API / vLLM): biên soạn lại nhật ký thô thành hướng dẫn sử dụng (nhãn, mô tả, tiêu đề, tóm tắt), tự động chia phần mục lục, có thể gộp/bỏ bước dư thừa.
- **Chế độ tự động 🤖**: bật checkbox ở cửa sổ chính là chỉ cần Ghi (F9) → thao tác → Dừng (F10); AI tự biên soạn, tự xuất HTML + lưu dự án vào `~/Documents/StepsRecorder/` và mở kết quả trong trình duyệt — không cần thao tác gì thêm. Nếu AI lỗi, ứng dụng quay về cửa sổ chỉnh sửa như thường.
- **🎨 AI tạo HTML trực quan** (nút riêng, khác với xuất HTML template): AI tự thiết kế toàn bộ trang — bố cục, CSS, mục lục — theo nội dung từng bản ghi. Chạy theo **vòng lặp tiếp nối (agentic loop)**: nếu một request chưa viết xong trang (bị cắt vì giới hạn token hoặc chưa đóng `</html>`), ứng dụng tự yêu cầu AI viết tiếp từ chỗ dừng — tối đa 6 lượt, có cắt đoạn trùng ở mối nối và hiển thị tiến độ từng lượt. Ảnh chụp không đi qua AI: AI chỉ chèn placeholder, ứng dụng gắn ảnh thật vào sau; ảnh nào AI không đặt sẽ gom vào "Phụ lục ảnh" để không mất dữ liệu.
- Timeout mỗi request AI cấu hình được ("Timeout (giây)" trong ⚙ Cấu hình, mặc định 600s); hết giờ sẽ báo lỗi rõ ràng kèm hướng khắc phục thay vì lỗi kỹ thuật khó hiểu.
- **💬 Trợ lý hỏi làm rõ** (bật/tắt trong ⚙ Cấu hình, mặc định bật): trước khi biên soạn — kể cả ở chế độ tự động và AI tạo HTML — AI xem nhật ký và nếu còn điểm quan trọng chưa rõ (tài liệu cho ai, bước mơ hồ nghĩa là gì, thuật ngữ nội bộ...) sẽ hỏi lại tối đa 3 câu kèm gợi ý trả lời, giống cách một trợ lý con người làm rõ yêu cầu trước khi bắt tay vào việc. Có thể hỏi thêm một lượt nữa nếu cần (tối đa 2 lượt); bỏ qua lúc nào cũng được và mọi lỗi ở pha hỏi không bao giờ chặn việc biên soạn.
- Xuất báo cáo HTML tự chứa (ảnh nhúng base64), có mục lục theo phần và bước.
- Xuất Markdown (`.md`) kèm thư mục ảnh `*_assets` — hiển thị được trên GitHub / VS Code; khi chia sẻ hãy gửi kèm thư mục ảnh.
- Xuất tài liệu Word (`.docx`) với tiêu đề, phần, bước và ảnh nhúng — tiện chỉnh sửa tiếp trong Microsoft Word.
- Lưu / mở lại dự án (`.steps.json`) để tiếp tục chỉnh sửa sau.

## Cài đặt

Yêu cầu Python 3. Cài các thư viện phụ thuộc:

```bash
pip install -r requirements.txt
```

Tính năng AI gọi API qua `urllib` (thư viện chuẩn Python) nên không cần cài thêm gì.

## Sử dụng

```bash
python main.py
# hoặc
python -m steps_recorder
```

Trong cửa sổ chính, bấm nút **⚙ Cấu hình** để thiết lập kết nối AI (base URL, model, API key, mục đích tài liệu, ngôn ngữ đầu ra...).

Phím tắt khi ghi: **F9** bắt đầu / tạm dừng / tiếp tục, **F10** dừng và mở cửa sổ chỉnh sửa. Lưu ý phím tắt chỉ được "lắng nghe" chứ không bị chặn — ứng dụng đang có tiêu điểm vẫn nhận được phím F9/F10.

## Cấu trúc mã nguồn

```
main.py                    # launcher (PyInstaller dùng file này)
steps_recorder/
  __main__.py              # python -m steps_recorder
  models.py                # dataclass Step, hằng số dự án
  config.py                # AppConfig, preset AI
  ai.py                    # gọi API + phân tích/áp kết quả AI (hàm thuần)
  recorder.py              # bộ máy ghi: hook chuột/phím, chụp màn hình
  exporters.py             # xuất HTML / Markdown / DOCX
  element.py               # nhận diện phần tử UI (Windows, UIA)
  winutil.py               # DPI awareness (Windows)
  deps.py                  # guard import thư viện bên thứ ba
  gui/                     # giao diện Tkinter (theme, cửa sổ chính, review…)
```

## Kiểm thử & lint

```bash
pip install pytest ruff mypy
python -m pytest tests/
python -m ruff check .
python -m mypy
```

## Lưu ý

- Cấu hình ứng dụng (bao gồm API key) được lưu tại `~/.steps_recorder_config.json` dưới dạng plaintext (file được tạo với quyền `0600` — chỉ chủ sở hữu đọc/ghi) — không commit file này lên git (đã được loại trừ trong `.gitignore`).
- Chế độ riêng tư chỉ che nội dung **gõ phím**; ảnh chụp màn hình vẫn có thể chứa dữ liệu nhạy cảm hiển thị trên màn hình — hãy xoá/kiểm tra ảnh trong cửa sổ chỉnh sửa trước khi chia sẻ.
- Dự án đã lưu (`*.steps.json`) và báo cáo xuất ra (`*.html`) cũng được loại trừ khỏi git theo mặc định.
