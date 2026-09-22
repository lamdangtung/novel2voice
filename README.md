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

