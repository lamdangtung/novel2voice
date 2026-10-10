# novel2voice 🎙️📖

Tool tự động hóa quy trình sản xuất truyện Audio (Audiobook):
1. **Dịch thuật tiểu thuyết (EN -> VI)** bằng AI (OpenAI GPT-4o, GPT-4o-mini hoặc các model tương thích) với văn phong trau chuốt, giữ sắc thái hội thoại và hỗ trợ từ điển thuật ngữ / nhân vật (`glossary.csv`).
2. **Chuyển văn bản thành giọng đọc (Text-to-Speech)** chất lượng cao với **Edge-TTS** (miễn phí, giọng tiếng Việt tự nhiên) hoặc **OpenAI TTS**.
3. **Phân đoạn & Ghép nối audio tự động** bằng `ffmpeg` xử lý mượt mà các chương truyện dài hàng nghìn từ.

---

## 📁 Cấu trúc thư mục

```
novel2voice/
├── input/                  # Thư mục đặt các file truyện tiếng Anh (.txt)
├── output/                 # Thư mục lưu bản dịch tiếng Việt (.txt) và file audio (.mp3)
├── glossary.csv            # Danh sách đối chiếu thuật ngữ / tên riêng (en, vi)
├── requirements.txt        # Các thư viện phụ thuộc
├── .env                    # Cấu hình API key, model, giọng đọc
└── src/
    ├── config.py           # Quản lý cấu hình
    ├── glossary.py         # Xử lý thuật ngữ
    ├── translator.py       # Module dịch thuật LLM
    ├── text_chunker.py     # Phân đoạn văn bản thông minh
    ├── tts.py              # Xử lý Text-to-Speech (Edge-TTS, OpenAI)
    ├── audio_merger.py     # Ghép file mp3 bằng ffmpeg
    ├── pipeline.py         # Luồng điều phối trọn gói
    └── main.py             # Giao diện dòng lệnh (CLI)
```

---

## 🚀 Cài đặt & Chuẩn bị

### 1. Kích hoạt môi trường ảo & cài đặt thư viện
```bash
# Kích hoạt venv
source .venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt
```

### 2. Cài đặt ffmpeg (đã có sẵn trên máy)
Đảm bảo máy đã cài `ffmpeg` để ghép audio:
```bash
ffmpeg -version
```

### 3. Cấu hình `.env`
Sao chép hoặc chỉnh sửa file `.env`:
```ini
# API Key cho bước dịch thuật (bắt buộc nếu dùng lệnh process hoặc translate)
OPENAI_API_KEY=your_openai_api_key_here
TRANSLATION_MODEL=gpt-4o-mini

# TTS Provider: "edge-tts" (miễn phí) hoặc "openai"
TTS_PROVIDER=edge-tts

# Giọng đọc mặc định:
# - vi-VN-HoaiMyNeural: Giọng nữ truyền cảm
# - vi-VN-NamMinhNeural: Giọng nam trầm ấm
TTS_VOICE=vi-VN-HoaiMyNeural

# Tốc độ đọc (ví dụ: +0%, +10%, -5%)
TTS_RATE=+0%
```

---

## 🎯 Hướng dẫn sử dụng CLI

### 1. Xem danh sách giọng đọc tiếng Việt hỗ trợ
```bash
python -m src.main voices
```

### 2. Chạy toàn bộ quy trình: Dịch EN -> Audio VI (`process`)
- **Xử lý 1 file truyện:**
  ```bash
  python -m src.main process input/chapter_100.txt
  ```
  *Kết quả:*
  - Bản dịch tiếng Việt: `output/chapter_100_vi.txt`
  - File âm thanh hoàn chỉnh: `output/chapter_100.mp3`

- **Tùy chọn giọng nam và tăng tốc độ đọc 10%:**
  ```bash
  python -m src.main process input/chapter_100.txt --voice vi-VN-NamMinhNeural --rate "+10%"
  ```

- **Xử lý hàng loạt (Batch) toàn bộ thư mục `input/`:**
  ```bash
  python -m src.main process input/
  ```

---

### 3. Chỉ dịch truyện EN -> VI (`translate`)
Nếu bạn chỉ muốn dịch truyện trước để kiểm tra hoặc biên tập văn bản:
```bash
python -m src.main translate input/chapter_100.txt
```
Bản dịch sẽ được lưu tại `output/chapter_100_vi.txt`.

---

### 4. Chỉ chuyển file tiếng Việt thành Audio (`tts`)
- **Chuyển đổi 1 file tiếng Việt:**
  ```bash
  python -m src.main tts output/chapter_100_vi.txt
  ```

- **Xử lý cả thư mục nhiều file (Mỗi file ra 1 audio riêng):**
  Hệ thống tự động sắp xếp theo thứ tự số chương tự nhiên (Natural Sort: `chapter_1` -> `chapter_2` -> `chapter_10` -> `chapter_100`):
  ```bash
  python -m src.main tts output/
  ```

- **Gộp TẤT CẢ các file trong thư mục thành 1 file Audio duy nhất (`--combine` / `-c`):**
  Nếu bạn muốn nối liền nhiều chương thành một tập audiobook dài:
  ```bash
  python -m src.main tts output/ --combine -o output/toan_tap_truyen.mp3
  ```

---

## 📖 Quản lý thuật ngữ (`glossary.csv`)
File `glossary.csv` giúp cố định cách dịch tên riêng, nhân vật, danh xưng, địa danh để AI không dịch sai lệch giữa các chương:

```csv
en,vi
Erich,Erich
Belgorod,Belgorod
Bruno,Bruno
Mukden,Mukden
Kaiser,Hoàng đế (Kaiser)
Stasi,Stasi (Bộ An ninh Quốc gia)
Okhrana,Okhrana
Major von Humboldt,Thiếu tá von Humboldt
Reich,Đế chế Reich
```
AI dịch thuật sẽ tự động đưa các quy tắc này vào prompt để đảm bảo sự nhất quán tuyệt đối.


## Phase 1: Pipeline chương tiếng Việt → audio có checkpoint

Phase này nhận các file TXT tiếng Việt theo chương và dùng VieNeu theo cấu hình hiện tại. Không cần API key dịch thuật. Không bao gồm fetch web, dịch, video hoặc YouTube.

```bash
# Kiểm tra môi trường; không nạp model hoặc gọi mạng
python -m src.main doctor --provider vieneu

# Tạo audio từng chương; resume bật mặc định
python -m src.main tts input/ --provider vieneu

# Dừng bằng Ctrl+C rồi chạy lại cùng lệnh để tiếp tục
python -m src.main tts input/ --provider vieneu --resume

# Giữ các đoạn sau khi thành công, hữu ích khi biên tập nội dung
python -m src.main tts input/ --provider vieneu --no-cleanup

# Ghép các chương thành một audio; vẫn giữ MP3 riêng từng chương
python -m src.main tts input/ --provider vieneu --combine -o output/toan_tap.mp3

# Xem trạng thái
python -m src.main status

# Bắt buộc tạo lại, bỏ qua cache
python -m src.main tts input/ --provider vieneu --no-resume

# Chỉ thử một lần và dừng batch ngay khi gặp chương lỗi
python -m src.main tts input/ --provider vieneu --retries 0 --fail-fast
```

### Cơ chế lưu và khôi phục

- `output/.state/jobs.sqlite3`: trạng thái chương, đoạn, job ghép tập, số lần thử và lỗi.
- `output/.state/chunks/`: audio đoạn theo dấu vết nội dung và cấu hình provider.
- `output/.state/last_batch_report.json`: báo cáo batch gần nhất, gồm chương hoàn thành, lỗi, bị ngắt và chưa xử lý.
- Có thể đổi nơi lưu bằng `--state-dir`; dùng lại cùng thư mục này để resume.
- Mỗi batch TTS xử lý tối đa `--concurrency` đoạn để giới hạn bộ nhớ và lưu checkpoint thường xuyên. Với VieNeu CPU, đây là kích thước batch, không bảo đảm có từng ấy luồng inference chạy đồng thời.
- Chương hoàn thành chỉ được bỏ qua nếu file đầu ra hợp lệ và checksum khớp checkpoint. Đoạn còn trong cache được tái sử dụng theo nội dung, cấu hình và checksum đã lưu.
- Đổi nội dung hoặc cấu hình tạo một phiên chương mới. Với `--no-cleanup`, các đoạn không thay đổi có thể được tái sử dụng. Với cleanup mặc định, cache của chương thành công đã bị xóa nên chương đã sửa cần tạo lại các đoạn thiếu.
- Lỗi TTS, lỗi ghép hoặc Ctrl+C giữ các đoạn hoàn thành. `--retries 2` nghĩa là tối đa 3 lần thử trong một lần chạy; chỉ thử lại đoạn chưa thành công.
- Batch mặc định tiếp tục các chương khác khi một chương lỗi, nhưng kết thúc với mã lỗi. Không ghép tập nếu còn chương thất bại; file TXT rỗng được báo lỗi, không âm thầm bỏ qua.
- Audio được kiểm tra có stream âm thanh và thời lượng dương bằng ffprobe. Sau ghép kiểm tra thời lượng tổng với dung sai `max(1 giây, 2%)`. Kiểm tra kỹ thuật này không xác nhận giọng đọc đúng hoặc đủ từng từ.
- File cuối chỉ được thay thế sau khi ghép và kiểm tra thành công. Mỗi state-dir có khóa chống hai tiến trình xử lý chung checkpoint trong cùng thời điểm.
- MP3 cũ chưa có checkpoint không được tự coi là hoàn thành; lần chạy đầu với pipeline mới sẽ tạo lại các chương được chọn. Nên thử một chương với `-o` trỏ tới file mới trước khi chạy cả thư mục.
- Nếu tiến trình bị kill cưỡng bức, batch đang chạy có thể phải tạo lại; các batch đã checkpoint vẫn được giữ. Trạng thái `running`/`merging` cũ được khôi phục khi chạy lại cùng lệnh.

### Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Bộ kiểm thử dùng TTS giả và FFmpeg/ffprobe thật để kiểm tra resume, retry, ngắt giữa chừng, đổi nội dung/giọng, audio hỏng, lỗi ghép và xử lý batch. Không tải model hoặc gọi dịch vụ TTS.
