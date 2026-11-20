# novel2voice

**Từ chương truyện đến audiobook tiếng Việt và video YouTube.**

novel2voice là ứng dụng Python giúp lấy truyện từ web hoặc đọc file TXT, dịch sang tiếng Việt, tạo audio, render video ảnh nền tĩnh và upload YouTube. Bạn có thể chạy từng bước bằng dòng lệnh hoặc quản lý hàng đợi và lịch công khai qua Telegram.

```text
TXT / URL chương → Bản dịch tiếng Việt → Audio từng chương
                                           ↓
                        Metadata + ảnh nền → Video → YouTube
```

[Bắt đầu cài đặt](docs/SETUP_A_Z_VI.md) · [Cấu hình mẫu](.env.example) · [Tham chiếu kỹ thuật](docs/REFERENCE_VI.md) · [Roadmap](roadmap.md)

## Mục lục

- [Tính năng](#features)
- [Yêu cầu môi trường](#requirements)
- [Bắt đầu nhanh](#quickstart)
- [Cấu hình provider](#providers)
- [Các luồng sử dụng](#workflows)
- [Video và metadata](#video)
- [Upload YouTube](#youtube)
- [Điều khiển qua Telegram](#telegram)
- [Tiếp tục công việc và lưu dữ liệu](#operations)
- [Cấu trúc project](#structure)
- [Kiểm thử](#testing)
- [Tài liệu và giới hạn](#documentation)

<a id="features"></a>

## Tính năng

| Nhóm | Khả năng |
|---|---|
| Nguồn truyện | Đọc TXT, xử lý thư mục theo số chương, lấy chương từ `ixdzs8.com` |
| Dịch thuật | OpenAI/endpoint tương thích hoặc DeepSeek native; hỗ trợ nội dung gốc tiếng Anh và tiếng Trung |
| Thuật ngữ | Glossary CSV theo truyện, tự tích lũy tên riêng và thuật ngữ khi bật |
| Giọng đọc | Edge-TTS, OpenAI TTS, Piper và VieNeu |
| Audio | MP3 từng chương, tùy chọn gộp nhiều chương; checkpoint và retry theo đoạn |
| Video | Chia tập theo số chương, render ảnh nền + audio, tạo thumbnail và thông tin thời lượng |
| Metadata | JSON thủ công hoặc LLM tạo nội dung theo tập kết hợp cấu hình truyện |
| YouTube | OAuth, upload có thể tiếp tục, chống tải trùng, thumbnail và lịch công khai |
| Telegram | Menu, hàng đợi tuần tự, tiến độ, retry và lịch 5 chương/ngày |

Không cần cấu hình tất cả dịch vụ. Nếu đã có TXT tiếng Việt, bạn có thể bắt đầu ngay ở bước tạo audio.

<a id="requirements"></a>

## Yêu cầu môi trường

- **Python 3.12**: phiên bản dùng trong môi trường đã kiểm tra của project.
- **FFmpeg và ffprobe**: cần cho tạo/ghép audio, kiểm tra media và render video.
- **macOS hoặc Linux**: checkpoint và bot sử dụng `fcntl`. Trên Windows, dùng WSL2/Linux; Windows native chưa được hỗ trợ đầy đủ.
- **Kết nối mạng và tài khoản phù hợp** cho backend dịch, TTS online và các tích hợp bạn chọn. Model TTS local có thể cần tải ở lần dùng đầu.

SQLite được tích hợp trong Python; không cần cài máy chủ database, Node.js hoặc Docker để chạy luồng chính.

<a id="quickstart"></a>

## Bắt đầu nhanh

Các bước dưới đây dành cho một bản cài mới và thử tạo audio từ tiếng Việt bằng Edge-TTS. Nếu đã có `.venv` hoặc `.env`, dùng lại cấu hình hiện có thay vì tạo đè. Xem [guide A–Z](docs/SETUP_A_Z_VI.md) để cài theo hệ điều hành và thiết lập từng dịch vụ.

### 1. Chuẩn bị công cụ

Trên macOS đã cài Homebrew:

```bash
brew install git python@3.12 ffmpeg
```

Trên Linux/WSL, cài Python 3.12, gói venv, Git và FFmpeg bằng công cụ quản lý của hệ điều hành. Kiểm tra trước khi tiếp tục:

```bash
python3.12 --version
ffmpeg -version
ffprobe -version
```

### 2. Lấy mã nguồn và cài thư viện

```bash
git clone --recurse-submodules https://github.com/lamdangtung/novel2voice.git
cd novel2voice

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Đã clone nhưng thiếu DeepSeek submodule? Chạy `git submodule update --init --recursive` từ thư mục gốc.

`requirements.txt` bao gồm VieNeu, ngay cả khi bài thử này chọn Edge-TTS. Nếu venv được tạo bằng `uv` và không có pip, dùng `uv pip install --python .venv/bin/python -r requirements.txt`. Hướng dẫn [cài chọn lọc thư viện](docs/SETUP_A_Z_VI.md#4-lấy-mã-nguồn-và-tạo-môi-trường) có trong guide.

### 3. Chọn giọng đọc cho lần chạy đầu

Chỉnh các biến tương ứng trong `.env`:

```ini
TTS_PROVIDER=edge-tts
TTS_VOICE=vi-VN-HoaiMyNeural
TTS_RATE=+0%
MAX_CHUNK_CHARS=2000
TTS_CONCURRENCY=3
```

Mẫu `.env.example` chọn **Piper**, nên cần đổi sang Edge-TTS cho bài thử này hoặc chuẩn bị đủ thư viện/model Piper. Bước `tts` không cần API key dịch thuật.

### 4. Tạo audio đầu tiên

```bash
mkdir -p input/demo output/demo
cat > input/demo/chapter_1_vi.txt <<'TXT'
Chương 1: Khởi đầu

Xin chào. Đây là đoạn thử giọng đọc tiếng Việt của novel2voice.
TXT

python -m src.main doctor --provider edge-tts
python -m src.main tts input/demo/chapter_1_vi.txt \
  --provider edge-tts -o output/demo/chapter_1.mp3
```

Mở `output/demo/chapter_1.mp3` bằng trình phát audio để nghe kết quả. `doctor` kiểm tra dependency và cấu hình cơ bản, chưa xác nhận dịch vụ online/model thực sự hoạt động hoặc chất lượng giọng đọc.

Mỗi lần mở Terminal mới, vào thư mục project và chạy `source .venv/bin/activate`. Tất cả ví dụ dưới đây dùng `python -m src.main` từ thư mục gốc.

### Chạy bằng file cấu hình

`process` và `tts` nhận file JSON cho một lần chạy. Các khóa trong file tương ứng
với tên tham số của lệnh; giá trị truyền trực tiếp bằng CLI luôn được ưu tiên.

```bash
python -m src.main tts --config configs/tts.json
python -m src.main tts --config configs/tts.json --provider edge-tts
```

Ví dụ [configs/tts.example.json](configs/tts.example.json):

```json
{
  "command": "tts",
  "vi_path": "input/my_story_vi",
  "provider": "vieneu",
  "voice": "Ngọc Lan",
  "rate": "+0%",
  "cleanup_temp": true,
  "combine": true,
  "concurrency": 3,
  "resume": true,
  "state_dir": "output/.state",
  "retries": 2,
  "continue_on_error": true,
  "background": null,
  "story_config": null,
  "video_title": "",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false,
  "youtube_metadata_file": null,
  "youtube_privacy": "private",
  "dry_run": false
}
```

`process` dùng cùng cơ chế với các khóa như `input_path`, `translation_provider`,
`model`, `provider`, `background`, `video_output_dir` và `upload_youtube`.

Xem [hướng dẫn cấu hình lần chạy](docs/HUONG_DAN_CAU_HINH_CHAY_VI.md) để biết
ý nghĩa chi tiết của từng tham số `process` và `tts`.

Sao chép mẫu [configs/process.example.json](configs/process.example.json) thành
file cấu hình riêng, thay đường dẫn và tham số, rồi chạy:

```bash
cp -n configs/process.example.json configs/process.json
python -m src.main process --config configs/process.json
```

<a id="providers"></a>

## Cấu hình provider

Ứng dụng tự đọc `.env`. Dùng [.env.example](.env.example) để tra các biến và [guide setup](docs/SETUP_A_Z_VI.md) để thiết lập chi tiết.

### Dịch thuật

| `TRANSLATION_PROVIDER` | Chuẩn bị | Model cấu hình |
|---|---|---|
| `openai` | `OPENAI_API_KEY`, endpoint OpenAI/tương thích | `TRANSLATION_MODEL` |
| `deepseek` | Submodule, dependency tùy chọn, Chromium và session web | `DEEPSEEK_MODEL`: `deepseek-chat` hoặc `deepseek-expert` |

Với OpenAI, đặt `OPENAI_BASE_URL=https://api.openai.com/v1` hoặc endpoint tương thích thực tế; tránh giá trị URL rỗng. Chọn model mà tài khoản/backend có quyền sử dụng.

DeepSeek native là client không chính thức dùng tài khoản web, không cần OpenAI API key hoặc server HTTP riêng. Thiết lập một lần:

```bash
python -m pip install -r requirements-deepseek.txt
python -m playwright install chromium
cd infra/Deepseek-API
python -m deepseek.auth
cd ../..
```

Dịch, học glossary và metadata dùng chung bộ giới hạn lượt gọi DeepSeek. Thời gian chờ/cooldown được lưu qua các lần chạy. Xem [cơ chế điều phối](docs/REFERENCE_VI.md#translation).

### Tạo giọng đọc

| `TTS_PROVIDER` | Nơi xử lý | Cấu hình cần chú ý |
|---|---|---|
| `edge-tts` | Online, không cần API key trong adapter | `TTS_VOICE`, `TTS_RATE`, `TTS_VOLUME`, `TTS_PITCH` |
| `openai` | API | Dùng chung key/base URL OpenAI; model hiện là `tts-1`, đổi giọng bằng `--voice` |
| `piper` | Local | Cài thêm `piper-tts`; tải cặp model ONNX/JSON, đặt `PIPER_MODEL_PATH` và `PIPER_CONFIG_PATH` |
| `vieneu` | Local hoặc remote | `VIENEU_MODE`, `VIENEU_VOICE`; mặc định mode `v3turbo`, SDK ghim `3.8.3` |

`--translation-provider` chọn **backend dịch**; `--provider` chọn **TTS**. `--model` của `translate`/`process` chọn model dịch. Tùy chọn giọng/tốc độ áp dụng theo từng adapter, không dùng chung voice ID giữa các provider.

Hướng dẫn riêng: [thiết lập TTS](docs/SETUP_A_Z_VI.md#7-thiết-lập-các-giọng-đọc) · [thiết lập dịch](docs/SETUP_A_Z_VI.md#8-thiết-lập-dịch-thuật).

<a id="workflows"></a>

## Các luồng sử dụng

Với các ví dụ bên dưới, thay đường dẫn bằng TXT có nội dung thực tế. Thư mục batch nên chứa riêng các chương của cùng một truyện, không trộn bản gốc, bản dịch và ghi chú.

### TXT tiếng Việt → audio

```bash
python -m src.main tts input/my_story_vi/chapter_1_vi.txt --provider vieneu

python -m src.main tts input/my_story_vi --provider vieneu --no-cleanup

python -m src.main tts input/my_story_vi --provider vieneu \
  --combine -o output/my_story_full.mp3
```

Mặc định `chapter_1_vi.txt` tạo `output/chapter_1.mp3`. Batch sắp xếp theo thứ tự số tự nhiên: 1, 2, 10. `--combine` vẫn giữ MP3 riêng từng chương; `--no-cleanup` giữ các đoạn audio để thuận tiện khi sửa nội dung.

### TXT đã dịch sẵn hoặc văn học tiếng Việt → audio/video

Dùng riêng lệnh `tts` cho nội dung đã có bằng tiếng Việt; lệnh này không gọi bước
dịch. Với một file đơn hoặc thư mục nhiều chương:

```bash
python -m src.main tts input/hai_dua_tre/hai_dua_tre.txt \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --background assets/background.jpg \
  --video-title 'Hai đứa trẻ'
```

```bash
python -m src.main tts input/truyen_vi \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --combine \
  --background assets/background.jpg \
  --story-config configs/story.json \
  --chapters-per-video 1 \
  --video-output-dir output/videos
```

Các tùy chọn `--story-config`, `--chapters-per-video`, `--video-output-dir` và
`--upload-youtube` có thể dùng trong cùng lệnh `tts`. Khi dùng `--story-config`,
file TXT tương ứng được gửi kèm MP3 để tạo tiêu đề, mô tả và thumbnail metadata.
Đặt `--upload-youtube` sau khi đã chạy `youtube-auth` và cấu hình OAuth/channel.

Mẫu cấu hình dành riêng cho nội dung tiếng Việt:

```bash
cp -n configs/vietnamese.example.json configs/vietnamese.json
python -m src.main tts --config configs/vietnamese.json
```

### Dry run cho luồng tiếng Việt

Dry run kiểm tra file TXT, ảnh nền, story config, kế hoạch chương/video và tùy
chọn upload mà không gọi TTS, FFmpeg, YouTube OAuth hay ghi audio/state:

```bash
python -m src.main tts --config configs/vietnamese.json --dry-run
```

Có thể bật trong JSON thay cho flag CLI:

```json
{
  "command": "tts",
  "vi_path": "input/hai_dua_tre",
  "dry_run": true
}
```

CLI `--dry-run` được ưu tiên so với giá trị `dry_run` trong file cấu hình.

### TXT gốc → bản dịch → audio

Chỉ dịch để đọc lại hoặc biên tập:

```bash
python -m src.main translate input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --glossary input/my_story/glossary.csv
```

Dịch và tạo audio trong một lệnh:

```bash
python -m src.main process input/my_story/chapter_1.txt \
  --translation-provider deepseek --provider vieneu \
  --glossary input/my_story/glossary.csv
```

Đầu ra mặc định là `output/chapter_1_vi.txt` và `output/chapter_1.mp3`. Đã có bản tiếng Việt thì dùng `tts`; `process` luôn thực hiện bước dịch. Đặt tên có mã truyện hoặc chọn output riêng để tránh hai truyện có cùng tên chương ghi vào một đường dẫn.

### Website → chương truyện

Hiện hỗ trợ URL chương HTTPS dạng `https://ixdzs8.com/read/<book>/p<number>.html`:

```bash
python -m src.main fetch 'https://ixdzs8.com/read/644938/p1.html' --max-chapters 2

python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 2 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv
```

`fetch` chỉ lấy nguồn, lưu TXT/JSON trong `input/web/<source>/<book>/`. `process` nối thêm dịch và audio; bản dịch/MP3 được lưu trong `output/`. Số chương mặc định là 1; chương tiếp theo được lấy theo liên kết trên trang, dừng sớm nếu hết chương.

### Glossary theo truyện

File CSV UTF-8 có hai cột `en,vi`; cột `en` cũng nhận thuật ngữ gốc tiếng Trung:

```csv
en,vi
Wall Street,Phố Wall
Kaiser,Hoàng đế
```

Truyền file bằng `--glossary`. Bật `GLOSSARY_AUTO_UPDATE=true` để học thuật ngữ bằng lượt LLM bổ sung; đặt `false` nếu chỉ muốn dùng danh sách đã chuẩn bị. Mặc định, thuật ngữ tự thêm cần ít nhất 3 lần xuất hiện trong 2 đoạn khác nhau; mục đã có không bị tự ghi đè. Glossary hỗ trợ tính nhất quán, nhưng bản dịch vẫn cần được đọc lại.

### Tra cứu lệnh

| Lệnh | Mục đích |
|---|---|
| `fetch` | Lấy chương từ nguồn web được hỗ trợ |
| `translate` | Dịch TXT hoặc thư mục TXT |
| `tts` | Tạo audio từ TXT tiếng Việt |
| `process` | Dịch + TTS; thêm video/upload khi được yêu cầu |
| `plan-videos` | Xem cách chia audio chương thành video |
| `render-video` | Render từ audio và ảnh nền có sẵn |
| `youtube-auth` | Đăng nhập OAuth và lấy channel ID |
| `youtube-upload` | Xem trước metadata hoặc upload MP4 |
| `youtube-status` | Xem trạng thái upload đã lưu |
| `telegram-bot` | Chạy bot và worker pipeline |
| `doctor` | Kiểm tra môi trường TTS cơ bản |
| `status` | Xem checkpoint TTS |
| `voices` | Hiển thị hai giọng Edge tiếng Việt được liệt kê trong project |

```bash
python -m src.main --help
python -m src.main tts --help
```

<a id="video"></a>

## Video và metadata

Chuẩn bị ảnh thật tại `assets/background.jpg` và các MP3 của cùng một truyện:

```bash
python -m src.main plan-videos output/chapter_1.mp3 output/chapter_2.mp3 \
  --chapters-per-video 2

python -m src.main render-video output/chapter_1.mp3 output/chapter_2.mp3 \
  --background assets/background.jpg --title 'Tên truyện | Chương 1–2' \
  --chapters-per-video 2 --output-dir output/videos
```

Mặc định mỗi video có một chương; có thể đổi bằng `VIDEO_CHAPTERS_PER_VIDEO` hoặc `--chapters-per-video`. Video dùng ảnh nền tĩnh, H.264/AAC, mặc định 1920×1080, 30 fps. Đặt `VIDEO_FONT_PATH` nếu cần chọn font hỗ trợ tiếng Việt.

Nếu muốn LLM viết metadata theo nội dung, sao chép [story config mẫu](configs/story.example.json), chỉnh thông tin truyện rồi cung cấp cặp audio/bản dịch:

```bash
cp -n configs/story.example.json configs/story.json

python -m src.main render-video output/chapter_1.mp3 \
  --translated-file output/chapter_1_vi.txt \
  --story-config configs/story.json --metadata-provider deepseek \
  --background assets/background.jpg
```

| File đầu ra | Nội dung |
|---|---|
| `<tập>.mp4` | Video hoàn chỉnh |
| `<tập>.jpg` | Thumbnail |
| `<tập>.json` | Thông tin render, thời lượng và mốc audio chương |
| `<tập>.episode.json` | Kết quả LLM và cache khi dùng story config |
| `<tập>.youtube.json` | Metadata upload khi dùng story config; có thể biên tập trước upload |

Có thể tự soạn JSON upload theo [mẫu YouTube](configs/youtube.example.json) thay cho metadata do LLM tạo. JSON render và JSON upload có vai trò/schema khác nhau. Xem [tham chiếu metadata](docs/REFERENCE_VI.md#video) để biết quy tắc ghép, cache và giới hạn dữ liệu.

<a id="youtube"></a>

## Upload YouTube

### Kết nối kênh một lần

1. Trong Google Cloud, bật YouTube Data API v3 và cấu hình OAuth consent screen/test users.
2. Tạo OAuth client loại **Desktop app**, lưu JSON tại `.secrets/youtube/client_secret.json`.
3. Cài dependency và đăng nhập:

```bash
python -m pip install -r requirements-youtube.txt
python -m src.main youtube-auth
```

Điền channel ID vừa được in ra vào `YOUTUBE_CHANNEL_ID` trong `.env`. Giữ `YOUTUBE_PRIVACY=private` cho lần thử đầu. [Guide YouTube](docs/SETUP_A_Z_VI.md#12-kết-nối-và-upload-youtube) giải thích đầy đủ từng bước.

### Xem trước và upload

```bash
python -m src.main youtube-upload output/videos/chapter_1.mp4 --dry-run
python -m src.main youtube-upload output/videos/chapter_1.mp4 --privacy private
python -m src.main youtube-status
```

`--dry-run` chỉ kiểm tra dữ liệu/file local. Lệnh upload tự dùng `.youtube.json` cùng tên nếu có; `--metadata-file` chọn JSON khác. JPG cùng tên được dùng làm thumbnail, hoặc truyền `--no-thumbnail` để bỏ qua.

### Từ website đến video và YouTube

Sau khi dịch, TTS, ảnh nền, story config và OAuth đều đã sẵn sàng:

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --background assets/background.jpg --story-config configs/story.json \
  --chapters-per-video 1 --upload-youtube --youtube-privacy private
```

Bỏ `--upload-youtube` để chỉ tạo file local. Khi chỉ cần thử lại upload, dùng `youtube-upload` với MP4 đã có để tránh dịch lại. Upload hoàn tất nghĩa là YouTube đã nhận video; kiểm tra trạng thái xử lý và công khai trong YouTube Studio.

<a id="telegram"></a>

## Điều khiển qua Telegram

Tạo bot qua @BotFather, điền token và numeric user ID được phép vào `.env`:

```ini
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_PROGRESS_INTERVAL_SECONDS=30
```

Sao chép [profile mẫu](configs/telegram.example.json) thành `configs/telegram.json`; chỉnh nguồn, story config, ảnh nền, glossary và provider. Đường dẫn tương đối trong profile tính từ thư mục chứa JSON. Có thể đặt `upload_youtube=false` để thử chỉ tạo video trước.

```bash
cp -n configs/telegram.example.json configs/telegram.json
python -m src.main telegram-bot --profiles configs/telegram.json
```

Bot chỉ nhận chat riêng từ user ID được phép. Gửi `/menu` để dùng nút bấm, xem lại và xác nhận thao tác. Lệnh gõ đầy đủ được thực hiện trực tiếp:

| Lệnh | Tác dụng |
|---|---|
| `/run wallstreet 1` | Xếp hàng chương 1 ngay |
| `/status`, `/status 12` | Xem danh sách hoặc chi tiết job ID 12 |
| `/schedule wallstreet 2 YYYY-MM-DD HH:MM` | Hẹn giờ **bắt đầu xử lý** |
| `/schedule-day wallstreet 10 YYYY-MM-DD 3` | Lập lịch **công khai** 15 chương trong 3 ngày |
| `/retry 12` | Thử lại job lỗi/bị ngắt, giữ lịch cũ |
| `/retry 12 YYYY-MM-DD HH:MM` | Đặt giờ công khai mới và retry |
| `/now 12` | Ưu tiên chạy/retry, bỏ lịch và cooldown upload nội bộ; upload private không hẹn công khai |
| `/cancel 12 13` | Hủy job đang chờ |
| `/clear finished`, `/clear failed` | Ẩn lịch sử đã kết thúc, giữ file/checkpoint |

Thay `YYYY-MM-DD HH:MM` bằng thời điểm tương lai theo giờ Việt Nam (`Asia/Ho_Chi_Minh`). Với lịch 5 chương/ngày, giờ mặc định là **06:30, 11:30, 17:00, 19:30, 22:00**; mỗi lệnh hỗ trợ 1–7 ngày và yêu cầu bật upload. Bot chuẩn bị trong 24 giờ trước từng mốc, gửi lịch công khai cho YouTube; worker chạy tuần tự nên cần chừa đủ thời gian xử lý.

Máy và bot cần đang chạy để nhận lệnh/bắt đầu job. Trên macOS có thể dùng `caffeinate -i python -m src.main telegram-bot --profiles configs/telegram.json` để giữ máy thức. Không cần mở cổng Internet; bot dùng long polling. Repo chưa có dịch vụ tự khởi động sau reboot.

Hướng dẫn chi tiết: [setup Telegram](docs/SETUP_A_Z_VI.md#13-điều-khiển-qua-telegram) · [lịch công khai](docs/SETUP_A_Z_VI.md#14-lên-lịch-công-khai) · [tham chiếu menu và hàng đợi](docs/REFERENCE_VI.md#telegram).

<a id="operations"></a>

## Tiếp tục công việc và lưu dữ liệu

| Bước | Khả năng tiếp tục |
|---|---|
| Fetch/dịch CLI | Chưa có checkpoint từng đoạn; chạy lại có thể tải/dịch lại |
| TTS | Tái sử dụng chương/đoạn hợp lệ theo nội dung, cấu hình và hash |
| Render | Bỏ qua video hoàn chỉnh còn khớp checkpoint; render dở làm lại từ đầu video đó |
| Upload | Dùng phiên đã lưu, truy vấn server và gửi tiếp từ offset được xác nhận |
| Telegram retry | Dùng manifest để tái sử dụng các bước hoàn tất; job bị ngắt cần retry sau restart |

**Chạy lại `process` bằng CLI vẫn chạy bước dịch.** Để làm lại một bước sau, gọi riêng `tts`, `render-video` hoặc `youtube-upload`.

Các tùy chọn TTS thường dùng: `--no-cleanup` giữ chunk sau thành công, `--no-resume` tạo lại audio, `--retries 2` cho tối đa 3 lần thử ở lớp runner, `--fail-fast` dừng batch khi gặp chương lỗi.

State mặc định nằm trong `output/.state/`: TTS ở `jobs.sqlite3`/`chunks`, video ở `video`, upload ở `youtube`, bot ở `telegram` và điều phối DeepSeek ở `deepseek_requests`. Khi sao lưu, giữ cả input, output, các sidecar, glossary CSV/database và cấu hình. Dừng tiến trình ghi trước khi copy database.

Không xóa state upload để giải quyết lỗi: có thể làm mất dấu vết chống tải trùng. Nếu phiên upload không rõ kết quả, metadata đã thay đổi hoặc video đã được đăng, kiểm tra YouTube Studio trước. Không chạy bot và CLI cùng ghi một chương/đầu ra.

Xem [khôi phục và sao lưu](docs/SETUP_A_Z_VI.md#15-vận-hành-khôi-phục-và-sao-lưu) và [bảng xử lý lỗi](docs/SETUP_A_Z_VI.md#17-xử-lý-lỗi). Giữ `.env`, OAuth token, session DeepSeek và database upload trong phạm vi riêng tư.

<a id="structure"></a>

## Cấu trúc project

```text
novel2voice/
├── .env.example               # Cấu hình mẫu
├── configs/                   # Mẫu story, YouTube và Telegram
├── docs/                      # Setup A–Z và tham chiếu kỹ thuật
├── infra/Deepseek-API/         # Submodule DeepSeek native client
├── input/                     # TXT đầu vào và nội dung nguồn đã lấy
├── models/                    # Model local, ví dụ Piper
├── assets/                    # Ảnh nền/font do người dùng chuẩn bị
├── output/                    # Bản dịch, MP3, video và .state
├── src/
│   ├── main.py                # CLI
│   ├── config.py              # Đọc cấu hình
│   ├── pipeline.py            # Điều phối các bước
│   ├── sources/               # Adapter nguồn truyện
│   ├── translation_providers/ # Backend dịch và giới hạn lượt gọi
│   ├── translator.py          # Dịch và áp dụng glossary
│   ├── glossary_manager.py    # Tích lũy thuật ngữ
│   ├── tts_providers/          # Edge, OpenAI, Piper, VieNeu
│   ├── tts_jobs.py            # Checkpoint và retry audio
│   ├── video/                 # Chia tập, ảnh và render
│   ├── publishing/            # Metadata, OAuth và upload
│   └── remote/                # Bot, menu và hàng đợi Telegram
├── tests/                     # Kiểm thử tự động
├── requirements.txt           # Thư viện chính, gồm VieNeu
├── requirements-deepseek.txt  # Dependency DeepSeek native tùy chọn
└── requirements-youtube.txt   # Dependency OAuth/YouTube tùy chọn
```

`input/`, `models/`, `assets/` và `output/` là dữ liệu cục bộ; bạn có thể cần tạo chúng trên một bản clone mới. File cấu hình mẫu không chứa sẵn credentials hoặc model.

<a id="testing"></a>

## Kiểm thử

Trong venv đã cài thư viện và có FFmpeg/ffprobe:

```bash
python -m unittest discover -s tests -v
```

Bộ test kiểm tra dịch, glossary, TTS checkpoint/retry, nguồn web, render, metadata, upload và Telegram. Các dịch vụ LLM/TTS/YouTube/Telegram được mô phỏng; một số bài media dùng FFmpeg/ffprobe thật. Test không gửi tin nhắn, tải model hoặc upload video thật; hãy chạy một mẫu thực tế trước khi sản xuất hàng loạt.

<a id="documentation"></a>

## Tài liệu và giới hạn

| Tài liệu | Khi nào đọc |
|---|---|
| [Setup A–Z](docs/SETUP_A_Z_VI.md) | Cài mới, thiết lập provider, OAuth/bot và xử lý lỗi |
| [Cấu hình môi trường](.env.example) | Tra biến `.env` và chọn nhóm cấu hình cần dùng |
| [Tham chiếu kỹ thuật](docs/REFERENCE_VI.md) | Cơ chế checkpoint, glossary, metadata, upload và lịch |
| [Story config mẫu](configs/story.example.json) | Khai báo thông tin cố định theo truyện |
| [YouTube metadata mẫu](configs/youtube.example.json) | Biên tập metadata thủ công cho một/nhiều video |
| [Telegram profile mẫu](configs/telegram.example.json) | Cấu hình truyện cho bot |
| [Roadmap](roadmap.md) | Định hướng mở rộng, cần phân biệt với code đã triển khai |

Phạm vi hiện tại: nguồn web chỉ có trang chương ixdzs8; video dùng ảnh tĩnh; mỗi job Telegram xử lý một chương thành một video. Chưa có web dashboard, tự theo dõi chương mới vô hạn, tạo Shorts/Reels, tự quản lý playlist hoặc cập nhật metadata cho video đã upload. Các thay đổi sau upload được thực hiện trong YouTube Studio.

Chất lượng bản dịch/giọng đọc, quyền tài khoản, hạn mức dịch vụ và thời gian xử lý YouTube cần được kiểm tra trong môi trường thực tế. Lịch và checkpoint giúp vận hành, nhưng không bảo đảm mọi job sẽ kịp giờ công khai.
