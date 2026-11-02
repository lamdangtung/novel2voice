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
    ├── tts.py              # Factory và public imports cho TTS
    ├── tts_providers/      # Base và các provider Edge, OpenAI, Piper, VieNeu
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

## Dịch bằng DeepSeek native client

Provider `deepseek` gọi trực tiếp `DeepSeekClient` trong `infra/Deepseek-API`,
không cần server HTTP hoặc OpenAI API key. Đây là cầu nối không chính thức tới
DeepSeek Chat, sử dụng session tài khoản đăng nhập trên máy.

```bash
# Tại thư mục gốc project, trong môi trường Python đã kích hoạt
pip install -r requirements-deepseek.txt
playwright install chromium

# Đăng nhập lần đầu
cd infra/Deepseek-API
python -m deepseek.auth
cd ../..

# Thử một chương; chọn file đầu ra riêng để kiểm tra
python -m src.main translate input/chapter_1.txt --translation-provider deepseek -o output/chapter_1_deepseek_vi.txt

# Chọn model Expert
python -m src.main translate input/chapter_1.txt --translation-provider deepseek --model deepseek-expert
```

Có thể đặt `TRANSLATION_PROVIDER=deepseek` và `DEEPSEEK_MODEL=deepseek-chat`
trong `.env`. Lệnh `process` cũng hỗ trợ `--translation-provider`;
`--provider` vẫn dành riêng cho TTS.

Các đoạn trong cùng chương dùng chung hội thoại, tắt thinking/search và chạy tuần tự.
Chỉ đoạn đầu của mỗi hội thoại gửi hướng dẫn dịch và glossary; các đoạn tiếp theo
chỉ gửi nội dung cần dịch, tiếp tục bằng `conversation_id` mới nhất.

Cấu hình giới hạn trong `.env`:

```ini
DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION=5
```

Giá trị phải >= 1. Ví dụ giới hạn 5: đoạn 1–5 dùng hội thoại A, đoạn 6–10
sang hội thoại B và gửi lại glossary ở đoạn 6. Mỗi chương mới luôn bắt đầu hội
thoại mới. Giới hạn tính theo đoạn văn bản sau khi chia (mặc định tối đa 4.000
ký tự/đoạn), không phải số chương. Hội thoại chỉ được nhớ trong lần chạy hiện tại.
OpenAI vẫn gửi hướng dẫn và glossary trên từng request vì implementation hiện tại
không giữ hội thoại.
Client được nạp khi bắt đầu dịch; thiếu session sẽ báo cách đăng nhập, không tự
mở trình duyệt. Chưa có checkpoint/resume cho dịch. Kiểm thử tự động dùng client
giả để không gửi nội dung hoặc yêu cầu đăng nhập.


## Tự động tích lũy glossary sau conversation

Mặc định, lệnh `translate` và `process` tự học thuật ngữ khi dùng glossary có
đường dẫn CSV. Sau mỗi conversation dịch (hoặc phần cuối chưa đủ số đoạn),
ứng dụng dùng một yêu cầu model riêng để trích xuất ứng viên từ bản gốc và bản
dịch. Với DeepSeek, yêu cầu trích xuất tạo **một conversation riêng**, không
làm thay đổi lịch sử hội thoại dịch và không tính vào giới hạn số đoạn dịch.
OpenAI hiện là stateless nên mỗi đoạn được xem như một conversation.

```ini
GLOSSARY_AUTO_UPDATE=true
GLOSSARY_MIN_OCCURRENCES=3
GLOSSARY_MIN_DISTINCT_CHUNKS=2
GLOSSARY_MAX_AUTO_ENTRIES=500
GLOSSARY_MAX_PROMPT_ENTRIES=100
GLOSSARY_MAX_CANDIDATES=2000
```

- Ứng viên phải thuộc nhóm tên người, địa danh, tổ chức, danh xưng hoặc thuật
  ngữ đặc thù. Model lọc từ thông dụng; code tiếp tục kiểm tra độ dài, định dạng,
  term trong bản gốc và cách dịch trong bản dịch.
- Chỉ thêm CSV khi đạt cả ngưỡng tổng số lần xuất hiện và số đoạn khác nhau.
  Tần suất do code đếm với ranh giới từ, chuẩn hóa Unicode, hoa/thường và khoảng trắng.
- Mỗi nội dung đoạn chỉ được đếm một lần cho một glossary, kể cả khi chạy lại.
  Nếu sửa nội dung, đoạn được coi là bằng chứng mới; chưa có cơ chế thay thế
  bằng chứng phiên bản cũ. Hai đoạn có nội dung giống hệt nhau cũng chỉ tính một.
- Không ghi đè mục đã có, kể cả mục do lần chạy trước tự thêm. Cách dịch xung
  đột được lưu trong bảng `conflicts` để xem lại. Ứng viên có nhiều cách dịch
  chưa được đưa vào CSV.
- CSV giữ hai cột `en,vi`. SQLite cạnh CSV (`glossary.csv.sqlite3`) giữ ứng viên,
  nội dung nguồn dùng làm bằng chứng, xung đột và dấu vết mục tự thêm. Dùng
  `--glossary` riêng cho từng bộ truyện để tránh trộn dữ liệu. Giữ SQLite cùng
  CSV khi sao lưu hoặc di chuyển để không mất thống kê và giới hạn mục tự thêm.
- Giới hạn 500 chỉ tính các mục tự thêm có dấu vết SQLite; mục thủ công không
  bị xóa. Tối đa 2.000 cặp ứng viên được lưu; khi đầy, ứng viên mới không được ghi thêm. Nội dung bằng chứng vẫn tăng theo truyện.
- Prompt chỉ chọn tối đa 100 term đã có, ưu tiên term xuất hiện nhiều trong
  các đoạn sắp dịch của conversation. Glossary được giữ ổn định trong một
  conversation; conversation kế tiếp đọc dữ liệu mới.
- Ghi CSV qua file tạm rồi thay thế, có khóa chống hai tiến trình cập nhật cùng
  lúc. CSV lỗi định dạng không bị ghi đè. Lỗi trích xuất hoặc cập nhật glossary
  được cảnh báo; bản dịch vẫn tiếp tục và phần bằng chứng đã lưu vẫn được giữ.

Đặt `GLOSSARY_AUTO_UPDATE=false` để tắt học thuật ngữ và các lời gọi trích xuất
bổ sung. Khi tắt, cách truyền glossary dịch giữ như trước. Việc lọc từ thông dụng
và xác định cách dịch vẫn phụ thuộc chất lượng model; nên kiểm tra CSV định kỳ.


## Lấy truyện từ website (ixdzs8)

Interface `NovelSource` và dữ liệu `Chapter` nằm trong `src/sources/base.py`.
Adapter `Ixdzs8Source` chỉ phụ trách HTTP và phân tích trang của website;
`source_fetcher.py` điều phối lấy liên tiếp và lưu file. Thêm website mới bằng
adapter triển khai `supports`, `fetch_chapter`, `close`, rồi đăng ký trong factory.
Pipeline không chứa selector hoặc quy tắc URL của từng website.

Cài dependency cập nhật trước khi chạy:

```bash
uv pip install --python .venv/bin/python -r requirements.txt

# Chỉ lấy hai chương, bắt đầu từ URL được chỉ định
python -m src.main fetch 'https://ixdzs8.com/read/644938/p1.html' --max-chapters 2

# Lấy truyện → dịch sang tiếng Việt + học glossary → tạo audio
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 2 \
  --translation-provider deepseek \
  --model deepseek-chat \
  --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv
```

Mặc định chỉ lấy **một chương**. `--max-chapters` là số chương tối đa từ URL
ban đầu; chương tiếp theo được lấy từ liên kết điều hướng trên trang, không tự
đoán URL. Hiện nhận URL chương `/read/<book>/p<number>.html`, chưa nhận URL mục
lục hoặc tự đồng bộ cả bộ truyện. Nếu hết chương, dừng sớm.

Bản gốc UTF-8 được lưu riêng, ví dụ:

```text
input/web/ixdzs8/644938/ixdzs8_644938_1_zh.txt
input/web/ixdzs8/644938/ixdzs8_644938_1_zh.json
```

File TXT gồm tiêu đề và nội dung chương. File JSON lưu URL, ID truyện/chương,
ngôn ngữ, liên kết tiếp theo và thời điểm tải. Menu, script và các khối quảng cáo
nhận diện được bị loại; ghi chú tác giả trong thân truyện vẫn được giữ nguyên.
Trang mẫu là tiếng Trung, nên prompt dịch đã mở rộng nhận ngôn ngữ gốc thay vì
chỉ tiếng Anh. Glossary vẫn giữ tên cột `en,vi` để tương thích; cột `en` có thể
chứa term tiếng Trung. Bộ đếm term hỗ trợ chữ Hán không có dấu cách.

`fetch --output-dir <folder>` đổi thư mục gốc lưu nguồn. `process URL` lấy các
chương trước rồi chạy pipeline hiện có lần lượt từng chương. `--output` chỉ dùng
với một chương. Tên đầu ra có ID nguồn và truyện để tránh đụng tên giữa các bộ.
Các lệnh xử lý file/thư mục cũ vẫn hoạt động.

Yêu cầu HTTP có timeout 30 giây và khoảng cách tối thiểu một giây trong cùng
adapter. Lỗi HTTP, trang rỗng/đổi cấu trúc và liên kết sai truyện sẽ báo lỗi; không
có cơ chế vượt chặn website. Chương đã lưu trước khi lỗi vẫn còn. Chạy lại `fetch`
sẽ tải lại và thay thế file gốc; chưa có cache/resume cho bước lấy truyện hoặc dịch.


## Số chương trong một video

File gốc, bản dịch TXT và audio vẫn lưu riêng theo từng chương. Cấu hình chia
video độc lập với cấu trúc lưu chương:

```ini
VIDEO_CHAPTERS_PER_VIDEO=1
```

Mặc định một video chứa một chương. Đổi thành `3` để video 1 chứa chương 1–3,
video 2 chứa chương 4–6. Nhóm cuối vẫn được tạo khi chưa đủ ba chương.

Xem kế hoạch bằng các audio chương đã có của **cùng một bộ truyện**:

```bash
python -m src.main plan-videos output/chapter_1.mp3 output/chapter_2.mp3 output/chapter_3.mp3

# Ghi đè cấu hình cho lần chạy này
python -m src.main plan-videos output/chapter_1.mp3 output/chapter_2.mp3 output/chapter_3.mp3 \
  --chapters-per-video 2
```

Chương được sắp xếp tự nhiên theo tên file. Chỉ truyền audio từng chương,
không truyền file audio đã ghép tập hoặc chương thuộc nhiều bộ truyện khác nhau.
Kế hoạch chỉ tham chiếu file hiện có, không gộp hoặc sửa TXT/audio. Số video
được đánh lại từ 1 theo danh sách đầu vào; chưa quản lý lịch sử video xuất bản.
Cấu hình này được dùng cho cả `plan-videos` và bước render MP4.


## Render video từ audio chương

Implementation `FFmpegVideoRenderer` triển khai interface `VideoRenderer`;
`VideoSpec` chứa danh sách audio, ảnh nền, tiêu đề và cấu hình hình ảnh.
`PillowThumbnailGenerator` triển khai interface riêng để chuẩn bị ảnh nền có
chữ và thumbnail mà không phụ thuộc bộ lọc font trong bản FFmpeg trên máy.

```bash
# Render từ audio đã có; không dịch/TTS lại
python -m src.main render-video output/chapter_1.mp3 output/chapter_2.mp3 \
  --background assets/background.jpg \
  --title 'Tên truyện' \
  --chapters-per-video 1

# Ghép hai chương vào một video, giữ nguyên audio chương
python -m src.main render-video output/chapter_1.mp3 output/chapter_2.mp3 \
  --background assets/background.jpg \
  --title 'Tên truyện — Chương 1–2' \
  --chapters-per-video 2 \
  --output-dir output/videos

# Chạy từ website đến video
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 2 \
  --translation-provider deepseek --model deepseek-chat --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --background assets/background.jpg \
  --video-title 'Tên truyện' \
  --chapters-per-video 1
```

Thay `assets/background.jpg` bằng ảnh thật của bạn. Với `process`, chỉ render
khi có `--background`; `--video-output-dir` đổi thư mục video. Với `render-video`,
`--output-dir` đổi thư mục kết quả. Số chương lấy từ `VIDEO_CHAPTERS_PER_VIDEO`
nếu không truyền `--chapters-per-video`.

```ini
VIDEO_CHAPTERS_PER_VIDEO=1
VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080
VIDEO_FPS=30
VIDEO_FONT_PATH=
```

Kích thước là số chẵn >= 16, FPS từ 1 đến 60. Có thể chỉ định font TTF/OTF hỗ
trợ tiếng Việt bằng `VIDEO_FONT_PATH`; mặc định tìm Arial/DejaVu trên máy rồi
fallback sang font Pillow. Cần font hỗ trợ chữ Hán nếu muốn tiêu đề tiếng Trung.

Mỗi nhóm xuất ba file trong `output/videos/`:

- `<chapter>.mp4`: video ảnh tĩnh, H.264/yuv420p, AAC 48 kHz stereo, faststart.
- `<chapter>.jpg`: thumbnail dùng cùng hình và tiêu đề, tối đa 1280×720.
- `<chapter>.json`: tiêu đề, file nguồn, thời lượng và mốc bắt đầu từng chương
  theo thời lượng audio nguồn (có thể lệch nhẹ do padding của định dạng MP3).

Nhóm nhiều chương dùng tên `<first>__to__<last>`. Ảnh nền được crop vừa khung,
không kéo méo; tiêu đề được xuống dòng trong dải nền tối. Video dài theo audio.
Chưa có zoom, nhạc nền, phụ đề hoặc intro/outro. Upload YouTube là bước riêng ở dưới.

Checkpoint lưu tại `output/.state/video/videos.sqlite3`. Chỉ bỏ qua video khi
nội dung audio, ảnh, font cấu hình, tiêu đề, thông số render và checksum cả ba
file kết quả khớp. `render-video --no-resume` bắt buộc tạo lại. Video được render
vào thư mục tạm, kiểm tra stream/kích thước/thời lượng trước khi thay file cuối.
Lỗi render hoặc bị ngắt giữ video cũ và các chương gốc; chạy lại bỏ qua video đã
hoàn thành và render lại video chưa xong từ đầu. Không resume ở giữa một video.
Resume này chỉ áp dụng cho render; chạy lại `process` vẫn chạy bước dịch hiện tại.


## Upload YouTube

`VideoPublisher` là interface chung. `YouTubePublisher` xử lý OAuth/HTTP và giao
thức resumable của YouTube; `PublishingRunner` quản lý checkpoint, retry và
chống upload trùng. Upload chỉ chạy với lệnh `youtube-upload` hoặc tùy chọn
`process --upload-youtube`. Mặc định là **private**, không tự công khai video.

### Chuẩn bị một lần

1. Trong [Google Cloud Console](https://console.cloud.google.com/), tạo/chọn project
   rồi bật **YouTube Data API v3**.
2. Cấu hình OAuth consent screen; thêm tài khoản của bạn vào Test users nếu ứng
   dụng đang ở chế độ Testing. Tạo OAuth client loại **Desktop app**.
3. Tải OAuth client JSON về `.secrets/youtube/client_secret.json` trong project.
   Không dùng API key hoặc service account thay OAuth tài khoản YouTube.
4. Cài dependency và đăng nhập:

```bash
uv pip install --python .venv/bin/python -r requirements-youtube.txt
python -m src.main youtube-auth
```

Lệnh mở trình duyệt cho bạn chọn tài khoản/kênh và cấp quyền upload, đọc thông
tin kênh. Nó không upload video. Sau khi đăng nhập, lệnh in ID kênh; thêm vào `.env`:

```ini
YOUTUBE_CLIENT_SECRETS_FILE=.secrets/youtube/client_secret.json
YOUTUBE_TOKEN_FILE=.secrets/youtube/token.json
YOUTUBE_CHANNEL_ID=UC_your_channel_id
YOUTUBE_PRIVACY=private
YOUTUBE_CATEGORY_ID=22
```

Thay giá trị channel ID bằng ID thật được in ra. Token refresh lưu cục bộ với
quyền đọc/ghi chỉ chủ file; `.secrets/` được git-ignore. Khi token bị thu hồi hoặc
hết hạn không refresh được, chạy lại `youtube-auth`. Upload không tự mở trình duyệt.

### Kiểm tra và upload video đã render

```bash
# Chỉ xem metadata/thumbnail sẽ dùng; không gọi mạng hoặc cần đăng nhập
python -m src.main youtube-upload output/videos/chapter_1.mp4 --dry-run

# Upload riêng tư; tự lấy title từ JSON render và thumbnail JPG cùng tên
python -m src.main youtube-upload output/videos/chapter_1.mp4

# Tùy chỉnh metadata; --tag có thể lặp lại
python -m src.main youtube-upload output/videos/chapter_1.mp4 \
  --title 'Tên truyện — Chương 1' \
  --description 'Nội dung mô tả video' \
  --privacy private \
  --tag 'truyện audio' --tag 'audiobook'

# Xem trạng thái đã lưu mà không gọi YouTube
python -m src.main youtube-status
```

Thay đường dẫn ví dụ bằng video thực tế của bạn. Có thể truyền nhiều MP4 cùng
lệnh. Không truyền `--title` thì mỗi video dùng tiêu đề JSON riêng, fallback sang
tên file. Có thể truyền `--channel-id` để ghi đè kênh .env; tài khoản OAuth phải
khớp kênh này trước khi upload. `--made-for-kids` đặt nội dung dành cho trẻ em;
mặc định là `--not-made-for-kids`. `--no-thumbnail` bỏ bước đặt thumbnail tùy chỉnh.
`--privacy` nhận `private`, `unlisted` hoặc `public`; public có nghĩa là yêu cầu
công khai video trên YouTube, nên chỉ chọn khi nội dung đã sẵn sàng.

### Chạy pipeline có upload

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --background assets/background.jpg --video-title 'Tên truyện' \
  --upload-youtube --youtube-privacy private
```

Luồng: fetch → dịch/học glossary → audio chương → render video → upload video +
thumbnail. `--upload-youtube` cần ảnh nền, OAuth token và channel ID đã cấu hình.
Khi chỉ cần thử lại upload, dùng `youtube-upload` với MP4 đã có để tránh dịch lại.

### Checkpoint và giới hạn hiện tại

- `output/.state/youtube/uploads.sqlite3` lưu hash video + channel ID, metadata,
  phiên resumable, offset byte, video ID, trạng thái thumbnail và lỗi. Có thể đổi
  đường dẫn bằng `YOUTUBE_STATE_DIR`. Giữ thư mục này khi chạy lại/sao lưu; mất
  checkpoint có thể tạo bản upload trùng. Phiên upload là dữ liệu nhạy cảm, không
  chia sẻ file SQLite. Mỗi state-dir chỉ cho một tiến trình upload tại một thời điểm.
- Khóa chống trùng dùng nội dung file và kênh, nên đổi tên file không tạo upload
  mới. Không thể nhận biết video bị encode lại hoặc đã upload thủ công ngoài app.
- Khi mất mạng, query server để lấy offset thực tế rồi gửi tiếp. Nếu mất phản hồi
  sau byte cuối, query session để lấy video ID; không tự tạo session mới khi chưa
  xác định kết quả. Session hết hạn/không truy vấn được sẽ báo lỗi, cần đối chiếu
  YouTube Studio trước khi xử lý lại state; chưa có cơ chế tự hòa giải trường hợp này.
- Video ID được commit trước bước thumbnail. Nếu thumbnail bị từ chối do quyền
  kênh/giới hạn ảnh, chạy lại cùng lệnh chỉ thử thumbnail. Có thể dùng
  `--no-thumbnail` để hoàn tất phần video. Ảnh hỗ trợ JPEG/PNG tối đa 2 MiB.
- Cùng video/kênh nhưng đổi metadata sẽ báo lỗi để tránh tạo bản trùng. Phiên bản
  này chưa cập nhật metadata hoặc đổi visibility cho video đã upload; sửa trong
  YouTube Studio. Có thể thay thumbnail bằng file JPG cùng tên rồi chạy lại.
- Thành công nghĩa là YouTube đã nhận video và trả video ID, chưa đảm bảo xử lý
  transcoding, kiểm duyệt hoặc xuất bản hoàn tất. Trạng thái hiển thị là do
  YouTube quyết định; chưa hỗ trợ lịch publish, playlist hoặc theo dõi processing.
- Đây là OAuth desktop cho CLI. Khi làm web app, cần thay lớp xác thực bằng OAuth
  web và quản lý token theo tài khoản; interface publisher/runner vẫn tái sử dụng.

Tài liệu chính thức: [OAuth desktop](https://developers.google.com/youtube/data/guides/auth/installed-apps),
[resumable upload](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol),
[videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert),
[thumbnails.set](https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set).


## Metadata YouTube từ file JSON

Dùng [file mẫu](configs/youtube.example.json), sao chép thành file riêng rồi chỉnh
nội dung theo truyện/chương của bạn. JSON là dữ liệu đầu vào cho upload, không
thay thế JSON kỹ thuật mà renderer tạo cạnh MP4.

```bash
# Kiểm tra metadata cuối cùng mà không gọi YouTube
python -m src.main youtube-upload output/videos/ixdzs8_644938_1_zh.mp4 \
  --metadata-file configs/youtube.example.json --dry-run

# Upload mới với metadata từ JSON
python -m src.main youtube-upload output/videos/ixdzs8_644938_1_zh.mp4 \
  --metadata-file configs/youtube.example.json

# Pipeline đầy đủ: thêm tùy chọn này vào lệnh process có --upload-youtube
# --youtube-metadata-file configs/youtube.example.json
```

File có thể là object phẳng cho một video:

```json
{
  "title": "Tên truyện | Chương 1 — Tên chương | Truyện audio",
  "description": "Tóm tắt ngắn đúng nội dung chương.\n\nThông tin bộ truyện và liên kết playlist.",
  "tags": ["tên truyện", "truyện audio", "audiobook tiếng Việt"],
  "hashtags": ["TruyenAudio", "Audiobook"],
  "default_language": "vi",
  "default_audio_language": "vi",
  "privacy": "private"
}
```

Để dùng chung một file cho nhiều chương, dùng cấu trúc trong file mẫu:

```json
{
  "schema_version": 1,
  "defaults": {
    "description": "Thông tin chung của bộ truyện",
    "tags": ["truyện audio"],
    "privacy": "private"
  },
  "videos": {
    "chapter_1.mp4": {"title": "Tên truyện | Chương 1", "description": "Mô tả riêng chương 1"},
    "chapter_2.mp4": {"title": "Tên truyện | Chương 2"}
  }
}
```

Key trong `videos` khớp **chính xác tên MP4**, có đuôi `.mp4`, không gồm thư mục.
Thứ tự ưu tiên: tùy chọn CLI được truyền rõ → mục riêng trong `videos` →
`defaults` → cấu hình môi trường/JSON renderer/tên file. Mảng tags/hashtags và
chapters được thay thế nguyên mảng khi ghi đè, không tự nối. Description riêng
cũng thay thế toàn bộ mô tả chung. Không khai báo title thì dùng title renderer.
Không có trường mẫu tự nội suy; đặt tiêu đề từng video bằng `videos`.

| Trường JSON | Cách xử lý |
|---|---|
| `title` | Tiêu đề YouTube, tối đa 100 ký tự |
| `description` | Mô tả đa dòng; dùng `\n` trong JSON; tổng sau khi nối chapters/hashtags tối đa 5.000 byte UTF-8 |
| `tags` | Array từ khóa, được gửi vào snippet.tags; `--tag` ghi đè toàn bộ array |
| `hashtags` | Array hashtag có hoặc không có `#`; loại trùng và nối cuối description; tối đa 60 |
| `thumbnail` | File JPG/PNG; đường dẫn tương đối tính từ thư mục chứa JSON. `null` tắt; thiếu thì dùng JPG cạnh MP4. `--no-thumbnail` luôn tắt |
| `default_language` | Ngôn ngữ metadata, ví dụ `vi` |
| `default_audio_language` | Ngôn ngữ lời đọc, ví dụ `vi` |
| `category_id` | ID danh mục dạng string, mặc định theo cấu hình hiện có |
| `privacy` | `private`, `unlisted`, `public`; JSON có thể yêu cầu public, nên xem dry-run trước |
| `made_for_kids` | Boolean khai báo đối tượng trẻ em; không phải tùy chọn tăng lượt xem |
| `contains_synthetic_media` | Boolean khai báo AI/nội dung tổng hợp qua API YouTube. Các file mẫu của project đặt `true` theo yêu cầu, tương ứng khai báo Yes; không do LLM quyết định |
| `notify_subscribers` | Boolean, mặc định true; yêu cầu YouTube thông báo người đăng ký, không đảm bảo mọi người đều nhận thông báo |
| `chapters` | Array `{ "start_seconds": 0, "title": "Mở đầu" }`, nối vào description |

Chapters cần ít nhất ba mốc, mốc đầu ở 0 giây, thứ tự tăng và mỗi phần dài ít
nhất 10 giây, kể cả phần cuối. Thời lượng lấy từ JSON renderer hoặc ffprobe khi
thiếu. Video một chương truyện không bắt buộc khai báo chapters; bạn chỉ nên
chia thành các phân đoạn nhỏ khi có mốc nội dung chính xác. Không tự tạo mốc từ
văn bản chưa được căn thời gian.

JSON sai kiểu dữ liệu, trường không hỗ trợ, key trùng, nội dung quá dài hoặc
thumbnail không hợp lệ sẽ báo lỗi trước khi OAuth/upload. `--dry-run` cũng kiểm
tra dữ liệu và file cục bộ nhưng không bắt buộc có channel ID.

Metadata JSON áp dụng khi tạo upload. Với video đã upload hoặc phiên upload
đang tồn tại, đổi metadata vẫn bị chặn để tránh upload trùng/ghi đè ngoài ý muốn.
Sửa video cũ trong YouTube Studio; việc cập nhật video cũ bằng JSON chưa triển khai.
Các checkpoint cũ với metadata mặc định vẫn được nhận diện như trước.

### Những yếu tố giúp video phù hợp và dễ tìm hơn

- **Title và thumbnail:** mô tả đúng câu chuyện, thể loại và số chương; thumbnail
  dễ đọc trên điện thoại. Dùng tên chương và điểm hấp dẫn thực tế, tránh hứa hẹn
  không có trong nội dung.
- **Description:** hai dòng đầu nêu nội dung cụ thể của chương, phía sau có thông
  tin bộ truyện, liên kết chương/playlist và lời mời theo dõi phù hợp.
- **Tags:** ưu tiên tên truyện, biến thể tên/cách viết và thể loại liên quan;
  YouTube nói tags thường có vai trò nhỏ hơn title, thumbnail, description.
- **Hashtags:** dùng vài hashtag sát nội dung; không thêm hashtag không liên quan.
- **Chapters:** giúp người nghe định vị các đoạn trong video dài khi có mốc đúng.
- **Ngôn ngữ và phụ đề:** ngôn ngữ hiện đã gửi qua API. Upload phụ đề có timestamp
  và title/description nhiều ngôn ngữ là các bước có thể bổ sung tiếp.
- **Playlist theo bộ truyện, end screen, cards và bình luận ghim:** giúp người xem
  tìm chương tiếp theo. Hiện chưa tự động tạo/đặt các thành phần này; có thể cấu
  hình trong YouTube Studio và đặt liên kết playlist trong description.
- **Nội dung và chất lượng nghe:** mở đầu rõ ràng, giọng đọc dễ nghe, ít khoảng
  trống/lặp, âm lượng nhất quán. Theo dõi CTR, thời lượng xem và retention trong
  Analytics để điều chỉnh. Chưa có bước phân tích Analytics trong app.

Metadata không bảo đảm trending hay được đề xuất. YouTube đánh giá cả lựa chọn
xem, thời lượng xem, mức độ hài lòng và độ phù hợp với từng người xem.
Nguồn: [tags](https://support.google.com/youtube/answer/146402),
[hashtags](https://support.google.com/youtube/answer/6390658),
[chapters](https://support.google.com/youtube/answer/9884579),
[search/discovery](https://support.google.com/youtube/answer/141805),
[video metadata API](https://developers.google.com/youtube/data/reference/rest/v3/videos).


## Metadata cố định theo truyện + dynamic theo video

Bước này là **lượt LLM riêng**, không gộp với dịch hoặc trích xuất glossary.
Interface `EpisodeMetadataGenerator` có implementation `LLMEpisodeMetadataGenerator`;
`MetadataComposer` ghép thông tin bằng code, không phụ thuộc nhà cung cấp LLM.

Sao chép `configs/story.example.json` thành cấu hình bộ truyện của bạn. Phần cố
định gồm `story_title`, `author` (tùy chọn), `genres`, `description_intro`,
`description_footer`, `playlist_url`, `source_url`, `base_tags`, `hashtags`,
ngôn ngữ, danh mục, privacy và các khai báo đối tượng/nội dung tổng hợp.
`story_title` bắt buộc, tối đa 70 ký tự. Các URL tùy chọn cần HTTPS.

Phần dynamic tạo từ **toàn bộ bản dịch của đúng các chương trong video**, theo
thứ tự audio, gồm điểm hấp dẫn làm title, summary, tags riêng và thumbnail_text.
LLM không quyết định privacy, khai báo trẻ em hoặc nội dung tổng hợp và không
được tự đoán timestamp. Tối đa 60.000 ký tự bản dịch cho một yêu cầu, điều chỉnh
bằng `METADATA_MAX_INPUT_CHARS`; nếu vượt, báo lỗi thay vì âm thầm cắt nội dung.
Chưa có bước tóm tắt nhiều tầng cho tập rất dài.

### Thử đầy đủ từ website đến upload

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --story-config configs/story.example.json \
  --background assets/background.jpg \
  --chapters-per-video 1 \
  --upload-youtube --youtube-privacy private
```

Thay ảnh nền bằng file thực tế của bạn. OAuth YouTube vẫn cần chuẩn bị như phần
trên. Có thể bỏ `--upload-youtube` để kiểm tra metadata và video cục bộ trước.
Không dùng `--youtube-metadata-file` đồng thời với `--story-config`; tùy chọn cũ
vẫn dành cho metadata được viết thủ công. Khi dùng story config, nên bỏ
`--video-title` để phần hình ảnh dùng tiêu đề đã được tạo cho từng tập.

Thứ tự: fetch → dịch/học glossary → TTS từng chương → chia nhóm video →
LLM tạo metadata tập → ghép thông tin bộ truyện → render → upload (nếu bật).

### Thử từ bản dịch/audio đã có

Không cần fetch/dịch/TTS lại:

```bash
python -m src.main render-video output/ixdzs8_644938_1_zh.mp3 \
  --translated-file output/ixdzs8_644938_1_zh_vi.txt \
  --story-config configs/story.example.json \
  --metadata-provider deepseek \
  --background assets/background.jpg \
  --output-dir output/story_metadata_test
```

Nhiều audio thì lặp `--translated-file` theo đúng thứ tự audio được truyền vào.
Pipeline tự giữ cặp bản dịch/audio khi sắp xếp chương. Có thể thêm
`--metadata-model deepseek-chat`; nếu không chọn provider/model thì lấy cấu hình
mặc định. Với `process`, metadata mặc định dùng provider/model đang chọn để dịch,
nhưng tạo client/hội thoại riêng.

Mỗi video sẽ có:

```text
<video>.mp4           video với tiêu đề tập
<video>.jpg           thumbnail dùng thumbnail_text riêng
<video>.json          metadata kỹ thuật render và mốc audio chương
<video>.episode.json  kết quả dynamic, danh sách bản dịch và cache key
<video>.youtube.json  metadata upload cuối cùng, có thể xem/sửa
```

Cách ghép:

- Title: tên truyện → điểm hấp dẫn của tập → tên chương đầu/cuối; tối đa 100 ký
  tự, phần cuối có thể được cắt khi dài. Nếu bản dịch không có dòng tiêu đề
  chương nhận diện được thì dùng tên file làm nhãn, không dùng một câu văn tùy ý.
- Description: summary → giới thiệu truyện → tên truyện/tác giả/thể loại → URL
  playlist/nguồn nếu có → footer. Hashtags được thêm khi dựng upload spec.
- Tags: tags cố định trước, tags tập sau; chống trùng không phân biệt hoa/thường
  và giữ trong giới hạn độ dài. Các tags cuối vượt giới hạn sẽ không được thêm.
- Video dùng title đầy đủ; thumbnail dùng chữ ngắn dynamic. Chapters/timestamp
  trong JSON render vẫn lấy từ audio; không tự tạo YouTube chapter markers khi
  chỉ có một chương hoặc không có các mốc đủ điều kiện.

Cache dựa trên bản dịch, thứ tự chương, cấu hình truyện, provider/model và phiên
bản prompt. Nội dung/cấu hình không đổi thì dùng lại dynamic, không gọi LLM thêm.
Metadata JSON sai định dạng hoặc thiếu trường sẽ dừng bước này, không tự upload
bằng dữ liệu chưa kiểm tra. JSON hợp lệ vẫn cần xem lại vì mô hình có thể viết
summary/tiêu đề chưa sát nội dung.

`youtube-upload` tự đọc `<video>.youtube.json` nếu không có `--metadata-file`:

```bash
python -m src.main youtube-upload output/story_metadata_test/ixdzs8_644938_1_zh.mp4 --dry-run
python -m src.main youtube-upload output/story_metadata_test/ixdzs8_644938_1_zh.mp4 --privacy private
```

`--metadata-file` vẫn ghi đè lựa chọn file tự động; CLI ghi đè trường tương ứng.
Có thể sửa `.youtube.json` trước khi upload. Chạy lại với cùng cache key giữ các
sửa đổi file này. Khi bản dịch/story config thay đổi hoặc dùng
`render-video --no-resume`, metadata được tạo lại và file chỉnh tay có thể bị thay
thế, nên sao lưu khi cần. Đổi metadata cho video đã upload vẫn bị chặn như trước;
chưa tự cập nhật video cũ trong YouTube Studio.


Khai báo AI cho luồng hiện tại: đặt `"contains_synthetic_media": true` trong story config hoặc metadata upload. Giá trị này được giữ khi ghép metadata và gửi thành `status.containsSyntheticMedia=true`. Với `.youtube.json` đã tạo trước đó, thêm trường này trực tiếp trước khi upload. Video đã upload cần cập nhật khai báo trong YouTube Studio; app chưa tự sửa video cũ.
