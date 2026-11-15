# Hướng dẫn setup novel2voice từ A–Z

> Đối chiếu với mã nguồn trong workspace ngày 08/11/2026. Hướng dẫn chính dùng macOS; Linux và Windows qua WSL được ghi riêng. Các lệnh chạy từ thư mục gốc project, trong môi trường Python đã kích hoạt, trừ khi có chỉ dẫn khác.
>
> Đây là hướng dẫn cài và vận hành phiên bản hiện có. Không cần triển khai các ý tưởng trong `roadmap.md` hoặc `technical_design_notes.md` để chạy ứng dụng.

## Mục lục

1. [Project làm được gì?](#1-project-làm-được-gì)
2. [Chọn cấu hình cần dùng](#2-chọn-cấu-hình-cần-dùng)
3. [Chuẩn bị máy](#3-chuẩn-bị-máy)
4. [Lấy mã nguồn và tạo môi trường](#4-lấy-mã-nguồn-và-tạo-môi-trường)
5. [Tạo và hiểu cấu hình](#5-tạo-và-hiểu-cấu-hình)
6. [Chạy thử audio đầu tiên](#6-chạy-thử-audio-đầu-tiên)
7. [Thiết lập các giọng đọc](#7-thiết-lập-các-giọng-đọc)
8. [Thiết lập dịch thuật](#8-thiết-lập-dịch-thuật)
9. [Chuẩn bị truyện và glossary](#9-chuẩn-bị-truyện-và-glossary)
10. [Từ truyện đến audio](#10-từ-truyện-đến-audio)
11. [Render video và metadata](#11-render-video-và-metadata)
12. [Kết nối và upload YouTube](#12-kết-nối-và-upload-youtube)
13. [Điều khiển qua Telegram](#13-điều-khiển-qua-telegram)
14. [Lên lịch công khai](#14-lên-lịch-công-khai)
15. [Vận hành, khôi phục và sao lưu](#15-vận-hành-khôi-phục-và-sao-lưu)
16. [Tra cứu cấu hình](#16-tra-cứu-cấu-hình)
17. [Xử lý lỗi](#17-xử-lý-lỗi)
18. [Kiểm tra hoàn tất và nguồn tham khảo](#18-kiểm-tra-hoàn-tất-và-nguồn-tham-khảo)

## 1. Project làm được gì?

novel2voice là ứng dụng dòng lệnh Python; có thể điều khiển từ xa qua bot Telegram. Không có web dashboard cần mở bằng trình duyệt.

Luồng đầy đủ:

```text
TXT tiếng Anh/Trung hoặc URL chương ixdzs8
  → lấy/lưu nội dung gốc nếu đầu vào là URL
  → dịch tiếng Việt + tích lũy thuật ngữ
  → tạo MP3 từng chương
  → chia nhóm chương thành video
  → tạo metadata theo truyện nếu được yêu cầu
  → render MP4 ảnh nền tĩnh + thumbnail
  → upload YouTube nếu được bật
```

| Phần | Khả năng hiện tại |
|---|---|
| Nguồn truyện | File TXT; thư mục TXT; trang chương HTTPS của `ixdzs8.com` |
| Dịch | `openai` hoặc `deepseek` native client |
| TTS | `edge-tts`, `vieneu`, `piper`, `openai` |
| Video | Ảnh có sẵn + tiêu đề + audio; H.264/AAC, mặc định 1920×1080, 30 fps |
| YouTube | OAuth, upload tiếp tục được, thumbnail, metadata JSON, chống tải trùng |
| Telegram | Menu, hàng đợi, retry, tiến độ, hẹn giờ bắt đầu, lịch 5 chương/ngày |
| Lưu trạng thái | File trên ổ đĩa + SQLite; không cần cài máy chủ database |

Các phần như phân tích Story Event, sinh hook/short script, render Shorts/Reels, theo dõi chương mới vô thời hạn hoặc dashboard trong tài liệu thiết kế chưa có lệnh triển khai tương ứng trong CLI hiện tại.

### Bản đồ thư mục

| Đường dẫn | Dùng để làm gì |
|---|---|
| `src/main.py` | Điểm chạy CLI và các tùy chọn lệnh |
| `src/config.py` | Đọc `.env`, xác định đường dẫn và giá trị mặc định |
| `src/pipeline.py` | Nối fetch, dịch, TTS, video và upload |
| `src/sources/`, `src/source_fetcher.py` | Lấy chương từ website |
| `src/translation_providers/` | Backend dịch và giới hạn lượt gọi DeepSeek |
| `src/translator.py`, `src/glossary*.py` | Dịch, chia ngữ cảnh và quản lý thuật ngữ |
| `src/tts_providers/`, `src/tts_jobs.py` | Giọng đọc và checkpoint từng đoạn |
| `src/video/` | Chia tập, tạo ảnh có chữ, render và kiểm tra video |
| `src/publishing/` | Metadata, OAuth, lịch công khai và upload |
| `src/remote/` | Telegram, quyền truy cập, menu và hàng đợi |
| `infra/Deepseek-API/` | Git submodule cho DeepSeek native client |
| `configs/` | Mẫu cấu hình truyện, upload và Telegram |
| `input/` | Văn bản đầu vào; nội dung lấy từ website |
| `models/` | Model local do bạn tải, ví dụ Piper |
| `assets/` | Ảnh nền bạn chuẩn bị |
| `output/` | Bản dịch, MP3, video và checkpoint |
| `tests/` | Bộ kiểm thử tự động |
| `generate_files.py` | Tạo 20 file TXT trống liên tiếp để nhập nội dung; không tự lấy truyện |

## 2. Chọn cấu hình cần dùng

Không cần đăng ký mọi dịch vụ ngay từ đầu.

| Mục tiêu | Những phần cần chuẩn bị |
|---|---|
| TXT tiếng Việt → MP3 | Python + FFmpeg + một TTS provider |
| TXT tiếng Anh/Trung → MP3 | Thêm backend dịch |
| Truyện → video | Thêm ảnh nền; có thể thêm story config |
| Video → YouTube | Thêm thư viện Google, OAuth và channel ID |
| Điều khiển bằng điện thoại | Thêm bot Telegram và profile truyện |

Để kiểm tra setup nhanh, bắt đầu bằng TXT tiếng Việt + Edge-TTS. Để dùng tổ hợp DeepSeek + VieNeu + Telegram, hoàn thành lần lượt phần 3–14; thử thành công từng bước trước khi chạy cả hàng loạt.

TTS local cần tải model ở lần đầu và có đủ RAM/ổ đĩa. Repo không công bố cấu hình phần cứng tối thiểu được bảo đảm, nên hãy thử một đoạn ngắn rồi một chương trên máy của bạn. Dịch vụ dịch, TTS online và upload cần mạng; TTS local có thể chạy offline khi model và dependency đã có đủ.

## 3. Chuẩn bị máy

### 3.1. Hệ điều hành và Python

Dùng Python **3.12** để bám theo môi trường hiện có của project. Workspace được kiểm tra với Python 3.12.14; đây không phải cam kết mọi thư viện sẽ chạy trên mọi Python mới hơn.

Nhiều module dùng `fcntl` để khóa file. Vì vậy, luồng checkpoint/bot hiện tại dành cho macOS/Linux. Trên Windows, dùng **WSL2 Ubuntu** và thực hiện toàn bộ việc cài/chạy trong WSL. Chỉ đổi cú pháp kích hoạt venv sang PowerShell không giải quyết được hạn chế này.

### 3.2. macOS

Nếu chưa có Homebrew, cài theo [trang Homebrew](https://brew.sh/), rồi mở Terminal mới và chạy:

```bash
xcode-select --install
```

Nếu máy đã có Command Line Tools, bỏ qua bước trên.

```bash
brew install git python@3.12 ffmpeg
python3.12 --version
git --version
ffmpeg -version
ffprobe -version
```

Cả `ffmpeg` lẫn `ffprobe` phải chạy được. Không cần giả định máy đã có FFmpeg như phần mở đầu README cũ.

### 3.3. Ubuntu/Linux/WSL

```bash
sudo apt update
sudo apt install -y git ffmpeg build-essential python3-venv fonts-dejavu-core
python3 --version
```

Nếu `python3` chưa phải 3.12, cài Python 3.12 bằng công cụ quản lý Python bạn dùng, rồi dùng `python3.12` ở phần tiếp theo. Không đổi Python hệ thống chỉ để chạy project. WSL cần hỗ trợ mở cửa sổ trình duyệt nếu bạn chọn DeepSeek native hoặc đăng nhập YouTube trực tiếp trong môi trường đó; các bước đăng nhập này chưa được kiểm tra trên WSL trong lần rà soát này.

## 4. Lấy mã nguồn và tạo môi trường

### 4.1. Máy mới

Chọn thư mục lưu project, sau đó:

```bash
git clone --recurse-submodules https://github.com/lamdangtung/novel2voice.git
cd novel2voice
```

Nếu đã clone nhưng thiếu submodule, chạy từ thư mục gốc:

```bash
git submodule update --init --recursive
git submodule status
```

`infra/Deepseek-API/deepseek/__init__.py` phải tồn tại nếu dùng DeepSeek. Không cần lấy nhánh mới nhất của submodule; giữ revision mà project đang tham chiếu.

### 4.2. Workspace trên máy hiện tại

```bash
cd /Users/lamdt/Desktop/novel2voice
```

Nếu đã có `.venv` đang hoạt động, kích hoạt và kiểm tra nó trước. Không xóa hoặc tạo đè môi trường hiện có chỉ để làm theo guide:

```bash
source .venv/bin/activate
python --version
python -c 'import sys; print(sys.executable)'
```

Trên máy mới, khi **chưa có** `.venv`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Mỗi lần mở Terminal mới cần vào đúng project và kích hoạt venv lại. Các lệnh trong guide dùng `python -m src.main`, không dùng `python src/main.py`.

### 4.3. Cài thư viện

Cách cài theo danh sách đầy đủ của repo:

```bash
python -m pip install -r requirements.txt
python -m pip check
```

`requirements.txt` đã bao gồm `vieneu==3.8.3`, ngay cả khi bạn chỉ chọn Edge-TTS. Cài đặt có thể mất thời gian vì dependency/model local; model được nạp/tải khi thực sự dùng provider.

Nếu chỉ muốn khởi động bằng Edge-TTS và chưa cài được VieNeu, có thể cài nhóm tối thiểu dùng cho luồng đó:

```bash
python -m pip install 'openai>=1.30.0' 'python-dotenv>=1.0.0' \
  'typer>=0.12.0' 'tqdm>=4.66.0' 'edge-tts>=6.1.0' \
  'rich>=13.0.0' 'httpx>=0.27' 'beautifulsoup4>=4.12' 'Pillow>=10.1'
```

Đây là cách cài chọn lọc, không tương đương môi trường đầy đủ trong `requirements.txt`. Sau đó bổ sung VieNeu khi cần. Không cần `pydub`, Redis, PostgreSQL, Node.js hay Docker cho luồng chính.

Nếu venv được tạo bằng `uv` và báo `No module named pip`, dùng công cụ `uv` đã cài:

```bash
uv pip install --python .venv/bin/python -r requirements.txt
uv pip check --python .venv/bin/python
```

Với dependency tùy chọn, thay tên requirements tương ứng. Không dùng `sudo pip`.

## 5. Tạo và hiểu cấu hình

### 5.1. Tạo `.env` mà không ghi đè dữ liệu cũ

```bash
cp -n .env.example .env
```

Nếu `.env` đã tồn tại, giữ file đó và chỉnh bằng trình soạn thảo. Giá trị ví dụ như `DIEN_API_KEY_CUA_BAN` bên dưới phải được thay bằng thông tin thật trên máy bạn.

Project tự đọc `.env` bằng `python-dotenv`; không cần chạy `source .env`. Biến đã được export trong Terminal có thể ưu tiên hơn file `.env`. Nếu chỉnh file mà ứng dụng vẫn dùng giá trị cũ, kiểm tra biến đang export và khởi động lại tiến trình.

### 5.2. Cấu hình ban đầu để thử audio

Trong `.env`, chỉnh các dòng tương ứng, tránh để một biến xuất hiện nhiều lần:

```ini
TTS_PROVIDER=edge-tts
TTS_VOICE=vi-VN-HoaiMyNeural
TTS_RATE=+0%
MAX_CHUNK_CHARS=2000
TTS_CONCURRENCY=3

TRANSLATION_PROVIDER=openai
TRANSLATION_MODEL=gpt-4o-mini
GLOSSARY_AUTO_UPDATE=false
```

Chưa cần API key nếu chỉ chạy `tts`. Giá trị `gpt-4o-mini` là mặc định trong code, không phải xác nhận tài khoản của bạn có quyền sử dụng model đó.

**Điểm cần sửa từ mẫu:** `.env.example` đặt `TTS_PROVIDER=piper`, còn code mặc định `edge-tts` khi không có biến. Sao chép mẫu rồi chạy ngay có thể lỗi thiếu model Piper. Hãy chủ động chọn provider.

Nếu dùng OpenAI trực tiếp, đặt URL rõ ràng:

```ini
OPENAI_API_KEY=DIEN_API_KEY_CUA_BAN
OPENAI_BASE_URL=https://api.openai.com/v1
```

Không để `OPENAI_BASE_URL=` rỗng khi dùng backend OpenAI: code đọc chuỗi rỗng trực tiếp và chuyển cho SDK. Nếu dùng endpoint tương thích OpenAI khác, điền URL và model mà endpoint đó hỗ trợ; cả dịch và OpenAI TTS cùng dùng key/base URL này.

### 5.3. Quy tắc đường dẫn

- `input`, `output` và glossary mặc định được tính từ thư mục repo qua `src/config.py`.
- Các đường dẫn bạn nhập qua CLI và nhiều biến `.env` tương đối được tính từ thư mục đang chạy lệnh. Vì vậy luôn chạy ở root project.
- Riêng đường dẫn trong `configs/telegram.json` được tính từ **thư mục chứa JSON**. Ví dụ `../assets/background.jpg` trỏ từ `configs` ra `assets`.
- Đường dẫn thumbnail trong JSON metadata tương đối cũng tính từ thư mục chứa JSON đó.
- Dùng dấu nháy quanh đường dẫn có khoảng trắng.

## 6. Chạy thử audio đầu tiên

Bài thử này dùng mạng cho Edge-TTS, không dịch và không gọi YouTube.

```bash
mkdir -p input/setup_demo output/setup_demo
cat > input/setup_demo/chapter_1_vi.txt <<'TXT'
Chương 1: Khởi đầu

Xin chào. Đây là đoạn kiểm tra giọng đọc tiếng Việt của novel2voice.
Nếu bạn nghe rõ câu này, bước tạo audio đã hoạt động.
TXT

python -m src.main --help
python -m src.main doctor --provider edge-tts
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider edge-tts \
  --output output/setup_demo/chapter_1.mp3
```

Kết quả mong đợi: file `output/setup_demo/chapter_1.mp3` không rỗng, nghe có tiếng Việt.

Trên macOS:

```bash
open output/setup_demo/chapter_1.mp3
```

Kiểm tra thời lượng:

```bash
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 output/setup_demo/chapter_1.mp3
python -m src.main status
```

`doctor` chỉ kiểm tra FFmpeg/ffprobe, dependency và một số cấu hình; không nạp model, không thử mạng và không bảo đảm chất lượng giọng. Phải tạo/nghe file thật để xác nhận TTS hoạt động.

## 7. Thiết lập các giọng đọc

### 7.1. Edge-TTS

Đã có trong requirements. Cấu hình như phần 5. Hai voice ID có sẵn trong danh sách của project:

```bash
python -m src.main voices
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider edge-tts --voice vi-VN-NamMinhNeural --rate '+10%' \
  -o output/setup_demo/chapter_1_edge_nam.mp3
```

`voices` hiển thị bảng cố định gồm Hoài My và Nam Minh, không truy vấn đầy đủ các giọng từ dịch vụ. `--rate`, `TTS_VOLUME`, `TTS_PITCH` được adapter Edge sử dụng. Không cần Microsoft API key trong implementation này.

### 7.2. VieNeu local

Repo đang ghim **3.8.3**; không tự đổi sang phiên bản mới chỉ vì tài liệu upstream có thêm mode mới.

```bash
python -m pip install 'vieneu==3.8.3'
```

Trong `.env`:

```ini
TTS_PROVIDER=vieneu
VIENEU_MODE=v3turbo
VIENEU_VOICE=
VIENEU_BACKBONE_DEVICE=cpu
VIENEU_CODEC_DEVICE=cpu
```

Ban đầu để `VIENEU_VOICE` trống để dùng giọng mặc định của model. Không dùng voice ID của Edge cho VieNeu. Các tên giọng trong comment/mẫu chỉ là ví dụ; giọng khả dụng phụ thuộc bản SDK/model.

```bash
python -m src.main doctor --provider vieneu
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider vieneu --concurrency 1 \
  -o output/setup_demo/chapter_1_vieneu.mp3
```

Lần đầu có thể tải model từ Hugging Face. Chờ tải/nạp hoàn tất; nếu model yêu cầu đăng nhập, đặt `HF_TOKEN` có quyền truy cập model. Chỉ tăng `TTS_CONCURRENCY` sau khi thử thành công.

Wrapper hỗ trợ `v3turbo`, `standard`, `fast`, `remote` theo cấu hình. Với mode/model khác, bạn chịu trách nhiệm chọn repo và thiết bị mà SDK 3.8.3 hỗ trợ; guide bắt đầu bằng CPU để tránh phụ thuộc GPU. `--rate` không được factory truyền vào VieNeu, nên đổi tùy chọn đó không đổi tốc độ đọc của provider này.

Remote mode cần một server đã có sẵn, không được project này tự khởi động:

```ini
VIENEU_MODE=remote
VIENEU_API_BASE=http://127.0.0.1:8000/v1
VIENEU_MODEL_NAME=TEN_MODEL_TREN_SERVER_CUA_BAN
```

URL trên là ví dụ cấu hình, phải khớp server thực tế. Voice cloning có ở lớp Python qua `ref_audio`/`ref_text`, nhưng CLI hiện chưa có tùy chọn clone giọng.

### 7.3. Piper local

Piper **chưa nằm trong** `requirements.txt`. Cài thêm:

```bash
python -m pip install piper-tts
mkdir -p models/piper
curl -fL \
  'https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx' \
  -o models/piper/vi_VN-vais1000-medium.onnx
curl -fL \
  'https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json' \
  -o models/piper/vi_VN-vais1000-medium.onnx.json
```

Các lệnh tải ghi vào hai tên file trên; chỉ chạy nếu chưa có model cần giữ. Model và JSON phải là một cặp tương ứng. [Kho model chính thức](https://huggingface.co/rhasspy/piper-voices/tree/main/vi/vi_VN/vais1000/medium) chứa cả hai file; cách cài gói được nêu trong [tài liệu Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).

```ini
TTS_PROVIDER=piper
PIPER_MODEL_PATH=models/piper/vi_VN-vais1000-medium.onnx
PIPER_CONFIG_PATH=models/piper/vi_VN-vais1000-medium.onnx.json
PIPER_NUM_WORKERS=4
```

```bash
python -m src.main doctor --provider piper
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider piper --concurrency 1 \
  -o output/setup_demo/chapter_1_piper.mp3
```

Adapter dùng `PiperVoice.load()` và `voice.synthesize()` trả audio chunks có `audio_int16_bytes`. Repo chưa ghim phiên bản Piper, vì vậy bài thử trên là bắt buộc để xác nhận tương thích. Khi chạy ổn định hãy ghi lại phiên bản đã cài. Thông báo lỗi nhắc `./scripts/setup_piper.sh` là thông báo cũ; script đó không có trong repo này.

Số worker thực tế trong batch được truyền từ `--concurrency`/`TTS_CONCURRENCY`; không nên chỉ tăng `PIPER_NUM_WORKERS` rồi kỳ vọng pipeline tự dùng nhiều worker hơn. Giọng Piper do model quyết định; factory không chuyển `--voice` hoặc `--rate` vào provider này.

### 7.4. OpenAI TTS

Cần key/base URL đã cấu hình như phần 5, sau đó:

```bash
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider openai --voice alloy \
  -o output/setup_demo/chapter_1_openai.mp3
```

Adapter hiện dùng model `tts-1`; CLI không có tùy chọn đổi model TTS. `process --model` chọn **model dịch**, không chọn model giọng đọc. `TTS_VOICE` trong `.env` được factory dùng cho Edge; OpenAI TTS mặc định `alloy`, hãy truyền `--voice` khi muốn thay. `--rate` cũng không được truyền vào OpenAI TTS trong implementation hiện tại.

## 8. Thiết lập dịch thuật

### 8.1. Chọn backend

| Lựa chọn | Cần gì | Cấu hình chính |
|---|---|---|
| OpenAI/tương thích OpenAI | API key, endpoint và quyền dùng model | `TRANSLATION_PROVIDER=openai` |
| DeepSeek native | Submodule, Playwright, Wasmtime, session đăng nhập web | `TRANSLATION_PROVIDER=deepseek` |

Hai tùy chọn CLI khác nhau:

- `--translation-provider`: backend **dịch**.
- `--provider`: backend **TTS**.

### 8.2. Chuẩn bị văn bản để thử dịch

```bash
cat > input/setup_demo/chapter_1_en.txt <<'TXT'
Chapter 1: A New Beginning

John opened the window. The city was waking up, and he knew his journey had just begun.
TXT
```

### 8.3. OpenAI hoặc endpoint tương thích

Trong `.env`:

```ini
TRANSLATION_PROVIDER=openai
OPENAI_API_KEY=DIEN_API_KEY_CUA_BAN
OPENAI_BASE_URL=https://api.openai.com/v1
TRANSLATION_MODEL=gpt-4o-mini
GLOSSARY_AUTO_UPDATE=false
```

```bash
python -m src.main translate input/setup_demo/chapter_1_en.txt \
  --translation-provider openai \
  -o output/setup_demo/chapter_1_openai_vi.txt
```

Mở bản dịch để kiểm tra đủ câu, đúng tên và không có phần giải thích ngoài truyện. Model/endpoint phải hỗ trợ lời gọi Chat Completions mà code đang dùng. Nếu tài khoản không có model mặc định, đổi `TRANSLATION_MODEL` hoặc truyền `--model` phù hợp.

### 8.4. DeepSeek native, không cần chạy server

Đây là client không chính thức dùng session web DeepSeek, không phải gọi API chính thức bằng DeepSeek API key. novel2voice nạp trực tiếp client trong submodule; không cần chạy `app.py`, Uvicorn, Docker hay cấu hình `OPENAI_BASE_URL` về localhost để dùng nhánh này.

```bash
git submodule update --init --recursive
python -m pip install -r requirements-deepseek.txt
python -m playwright install chromium
```

Trên Linux thiếu thư viện trình duyệt, có thể cần bước cài dependency hệ thống của Playwright:

```bash
python -m playwright install --with-deps chromium
```

Đăng nhập trong Terminal có thể mở cửa sổ trình duyệt:

```bash
cd infra/Deepseek-API
python -m deepseek.auth
cd ../..
```

Dùng cùng venv của project; không tạo/kích hoạt thêm `infra/Deepseek-API/venv`. Hoàn thành đăng nhập và bước xác minh trong trình duyệt, đợi chương trình lưu session rồi quay về root.

Trong `.env`:

```ini
TRANSLATION_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION=5
GLOSSARY_AUTO_UPDATE=false
```

```bash
python -m src.main translate input/setup_demo/chapter_1_en.txt \
  --translation-provider deepseek \
  -o output/setup_demo/chapter_1_deepseek_vi.txt
```

Hai tên model adapter chấp nhận: `deepseek-chat`, `deepseek-expert`.

```bash
python -m src.main translate input/setup_demo/chapter_1_en.txt \
  --translation-provider deepseek --model deepseek-expert \
  -o output/setup_demo/chapter_1_expert_vi.txt
```

Session và Chromium profile nằm trong `infra/Deepseek-API/session/`. Khi session không dùng được, chạy lại lệnh đăng nhập trên máy; pipeline/bot không tự mở trình duyệt yêu cầu bạn đăng nhập giữa job.

### 8.5. Giới hạn tốc độ và chia đoạn dịch

```ini
DEEPSEEK_REQUEST_MIN_GAP_SECONDS=20
DEEPSEEK_REQUEST_MAX_GAP_SECONDS=45
DEEPSEEK_MAX_REQUESTS_PER_MINUTE=3
DEEPSEEK_MAX_REQUESTS_PER_HOUR=60
DEEPSEEK_COOLDOWN_BASE_SECONDS=120
DEEPSEEK_COOLDOWN_MAX_SECONDS=1800
```

CLI, bot, glossary và metadata cùng đi qua bộ điều phối DeepSeek. Thời gian chờ trong log là hành vi có chủ đích; lỗi upstream có thể kéo dài cooldown. Nếu nhiều bản project/process dùng cùng tài khoản, cấu hình cùng **đường dẫn tuyệt đối** `DEEPSEEK_REQUEST_STATE_DIR` để chia sẻ state. Không xóa state để bỏ qua thời gian chờ.

Dịch đang chia tối đa **4.000 ký tự/đoạn** trong `NovelTranslator.translate_text()`. `MAX_CHUNK_CHARS` là cấu hình chia đoạn TTS trong pipeline, không đổi giới hạn dịch này. DeepSeek mặc định gom tối đa 5 đoạn trong một conversation; chương mới bắt đầu conversation mới. OpenAI gửi system prompt cho mỗi request.

## 9. Chuẩn bị truyện và glossary

### 9.1. File TXT

Dùng TXT UTF-8, nội dung không rỗng. Tên file có số chương giúp sắp đúng thứ tự:

```text
input/my_story/chapter_1.txt
input/my_story/chapter_2.txt
input/my_story/chapter_10.txt
```

CLI xử lý thư mục theo thứ tự tự nhiên 1, 2, 10, chỉ lấy `*.txt` ở cấp trực tiếp, không đệ quy xuống thư mục con. Không trộn bản gốc, bản dịch, ghi chú và truyện khác vào cùng thư mục chạy batch.

Tên mặc định của audio không có thư mục truyện riêng. Hai truyện đều dùng tên `chapter_1` sẽ cùng hướng đến `output/chapter_1.mp3`. Hãy đặt tên có mã truyện như `my_story_chapter_1.txt`, hoặc chỉ định output riêng ở lệnh xử lý một file. Khi render, chọn audio thuộc cùng một truyện.

### 9.2. Lấy từ website

Hiện chỉ hỗ trợ URL chương theo đúng dạng:

```text
https://ixdzs8.com/read/<book_id>/p<chapter_number>.html
```

Ví dụ chỉ lấy một chương, chưa dịch/TTS:

```bash
python -m src.main fetch 'https://ixdzs8.com/read/644938/p1.html' --max-chapters 1
```

Kết quả:

```text
input/web/ixdzs8/644938/ixdzs8_644938_1_zh.txt
input/web/ixdzs8/644938/ixdzs8_644938_1_zh.json
```

JSON lưu thông tin nguồn; TXT lưu tiêu đề và nội dung. `--max-chapters 2` theo liên kết chương tiếp theo và có thể lấy ít hơn nếu hết truyện. Không nhận URL mục lục, query/fragment, nguồn website khác hoặc redirect sang chương khác.

### 9.3. Glossary theo truyện

Tạo `input/my_story/glossary.csv` bằng trình soạn thảo, ví dụ:

```csv
en,vi
John,Giôn
Wall Street,Phố Wall
纽约,New York
```

Cột `en` giữ tên vì schema hiện có; vẫn chứa được thuật ngữ gốc tiếng Trung. Mỗi hàng đúng hai cột không rỗng; thuật ngữ chứa dấu phẩy cần được đặt trong dấu nháy theo chuẩn CSV.

```bash
python -m src.main translate input/setup_demo/chapter_1_en.txt \
  --translation-provider deepseek \
  --glossary input/my_story/glossary.csv \
  -o output/setup_demo/chapter_1_glossary_vi.txt
```

Bật học thuật ngữ sau khi dịch cơ bản đã ổn:

```ini
GLOSSARY_AUTO_UPDATE=true
GLOSSARY_MIN_OCCURRENCES=3
GLOSSARY_MIN_DISTINCT_CHUNKS=2
GLOSSARY_MAX_AUTO_ENTRIES=500
GLOSSARY_MAX_PROMPT_ENTRIES=100
GLOSSARY_MAX_CANDIDATES=2000
```

Hệ thống gọi LLM thêm để trích xuất thuật ngữ. Với mẫu quá ngắn, glossary chưa thêm gì là bình thường: mặc định cần ít nhất 3 lần xuất hiện trong ít nhất 2 đoạn gốc khác nhau. Bản dịch thủ công đã có được giữ; cách dịch mâu thuẫn được ghi nhận thay vì tự thay thế.

Đi kèm CSV sẽ có `glossary.csv.sqlite3` để tích lũy bằng chứng và `glossary.csv.lock` để khóa truy cập. Giữ database khi sao lưu. Lỗi trích xuất thường chỉ được cảnh báo và bản dịch vẫn tiếp tục; CSV sai định dạng khi được đọc để chọn prompt có thể làm bước dịch dừng.

## 10. Từ truyện đến audio

### 10.1. Chỉ tạo MP3 từ bản tiếng Việt

```bash
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider vieneu --no-cleanup
```

Không có `-o`, file trên tạo `output/chapter_1.mp3`: hậu tố `_vi` cuối tên bị bỏ khi đặt tên audio. Dùng `-o` như bài thử nếu muốn tránh trùng với dữ liệu hiện có.

Batch và ghép thành một MP3:

```bash
python -m src.main tts input/my_story_vi --provider vieneu --no-cleanup
python -m src.main tts input/my_story_vi --provider vieneu \
  --combine -o output/my_story_full.mp3
```

Thư mục `input/my_story_vi` phải do bạn tạo và chứa các TXT tiếng Việt có nội dung. `--combine` vẫn giữ MP3 từng chương; chỉ ghép khi toàn batch thành công. Với đầu vào thư mục, `--output` cần đi cùng `--combine`.

### 10.2. Chỉ dịch

```bash
python -m src.main translate input/setup_demo/chapter_1_en.txt \
  --translation-provider deepseek
```

Mặc định tạo `output/chapter_1_en_vi.txt`. Với thư mục:

```bash
python -m src.main translate input/my_story --translation-provider deepseek \
  --glossary input/my_story/glossary.csv
```

`translate` nhận file hoặc thư mục local, không nhận URL. Dùng `fetch` trước hoặc `process` cho URL. `--output` của `translate` chỉ áp dụng ở nhánh một file.

### 10.3. Dịch và tạo audio trong một lệnh

```bash
python -m src.main process input/setup_demo/chapter_1_en.txt \
  --translation-provider deepseek --provider vieneu \
  --glossary input/my_story/glossary.csv \
  -o output/setup_demo/chapter_1_en.mp3
```

Từ website:

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv
```

Kết quả mặc định cho ví dụ web:

```text
output/ixdzs8_644938_1_zh_vi.txt
output/ixdzs8_644938_1_zh.mp3
```

`process` **luôn đi qua bước dịch**. Đã có TXT tiếng Việt thì chạy `tts` để không gọi dịch lại. `--output` với URL chỉ dùng khi `--max-chapters 1`; ở nhánh thư mục local của `process`, code không chuyển output tùy chỉnh cho từng file.

### 10.4. Resume và retry

```bash
python -m src.main status
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider vieneu --no-cleanup --retries 2 \
  -o output/setup_demo/chapter_1_vieneu.mp3
```

Dừng TTS bằng Ctrl+C rồi chạy lại đúng lệnh để dùng checkpoint. `--retries 2` cho tối đa 3 lần thử ở lớp runner; Edge còn có retry nội bộ.

```bash
python -m src.main tts input/setup_demo/chapter_1_vi.txt \
  --provider vieneu --no-resume \
  -o output/setup_demo/chapter_1_vieneu.mp3
```

Lệnh trên buộc tạo lại audio. Batch mặc định tiếp tục chương sau nếu một chương lỗi; dùng `--fail-fast` để dừng sớm.

**Phân biệt khả năng tiếp tục:**

| Bước | Hành vi khi chạy lại |
|---|---|
| `translate` | Chưa có checkpoint đoạn dịch; dịch lại và có thể ghi đè bản dịch |
| `process` CLI | Chạy lại bước dịch trước; không có resume toàn pipeline tương đương bot |
| `tts` | Tái sử dụng chương/đoạn hợp lệ dựa trên nội dung, cấu hình và hash |
| `render-video` | Tái sử dụng video đã hoàn chỉnh nếu input/cấu hình/artifact còn khớp |
| Upload | Truy vấn offset server và dùng phiên upload đã lưu |
| Telegram retry | Tái sử dụng các bước hoàn tất qua manifest artifact của từng job |

Mặc định `--cleanup` xóa chunk TTS sau khi chương thành công; MP3 chương vẫn được tái sử dụng. Nếu muốn chỉnh nội dung và chỉ tạo lại đoạn thay đổi, giữ chunk bằng `--no-cleanup` từ đầu. Đổi giọng, model, phiên bản dependency hoặc cấu hình liên quan có thể khiến cache không còn khớp.

## 11. Render video và metadata

Ngoài ảnh nền có sẵn, project hỗ trợ tạo ảnh theo bản dịch, zoom nhẹ và crossfade bằng `--illustrate`. Xem [hướng dẫn minh họa Gemini](ILLUSTRATIONS_VI.md) để cấu hình, dùng cache và bật cho bot. Các ví dụ bên dưới trình bày chế độ ảnh nền thủ công.

### 11.1. Chuẩn bị ảnh và font

Đặt một ảnh thật do bạn chọn tại `assets/background.jpg`. Đổi đuôi của một file không phải ảnh không tạo ra ảnh hợp lệ. Nếu chưa có ảnh, chỉ để kiểm tra render có thể tạo nền màu trơn:

```bash
python - <<'PY'
from pathlib import Path
from PIL import Image
path = Path('assets/setup_demo_background.jpg')
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists():
    Image.new('RGB', (1920, 1080), '#182433').save(path)
print(path)
PY
```

Ví dụ render bên dưới dùng ảnh demo này. Khi dùng ảnh thật, thay đường dẫn tương ứng.

Nếu chữ Việt thiếu dấu hoặc font lỗi, đặt font TTF/OTF hỗ trợ tiếng Việt:

```ini
VIDEO_FONT_PATH=/System/Library/Fonts/Supplemental/Arial.ttf
```

Đó là đường dẫn font ứng viên trên macOS; kiểm tra file tồn tại. Linux thường có `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` khi cài `fonts-dejavu-core`.

### 11.2. Render từ MP3 có sẵn

```bash
python -m src.main plan-videos output/setup_demo/chapter_1.mp3
python -m src.main render-video output/setup_demo/chapter_1.mp3 \
  --background assets/setup_demo_background.jpg \
  --title 'Truyện thử nghiệm | Chương 1' \
  --output-dir output/setup_demo/videos
```

Các file tạo ra:

```text
output/setup_demo/videos/chapter_1.mp4
output/setup_demo/videos/chapter_1.jpg
output/setup_demo/videos/chapter_1.json
```

`chapter_1.json` chứa thông tin render, thời lượng và mốc audio; chưa phải file metadata upload đầy đủ. Render có tiêu đề thủ công và không có `--story-config` không cần LLM.

### 11.3. Gom nhiều chương

Khi đã có các MP3 tương ứng:

```bash
python -m src.main plan-videos \
  output/my_story_chapter_1.mp3 output/my_story_chapter_2.mp3 \
  --chapters-per-video 2

python -m src.main render-video \
  output/my_story_chapter_1.mp3 output/my_story_chapter_2.mp3 \
  --chapters-per-video 2 \
  --background assets/setup_demo_background.jpg \
  --title 'Tên truyện' --output-dir output/my_story_videos
```

Video nhóm có tên `my_story_chapter_1__to__my_story_chapter_2.mp4`. Không gộp TXT, không xóa audio từng chương. Nhóm cuối có thể ít hơn số chương yêu cầu. Khi dùng wildcard như `output/my_story_chapter_*.mp3`, kiểm tra chỉ chọn chương của một truyện và không chứa file audio đã gộp.

### 11.4. Metadata theo nội dung truyện

Sao chép cấu hình mẫu, giữ nguyên bản mẫu:

```bash
cp -n configs/story.example.json configs/story.json
```

Chỉnh tối thiểu `story_title`, phần mô tả, tags và thể loại theo truyện. Schema mẫu đã có `privacy=private` và `contains_synthetic_media=true`; đọc và chỉnh các trường cho đúng nội dung bạn xuất bản. `story_title` cần 1–70 ký tự. Các trường mới không nằm trong schema sẽ bị từ chối.

Tạo metadata từ bản dịch thật cùng audio:

```bash
python -m src.main render-video output/setup_demo/chapter_1.mp3 \
  --translated-file input/setup_demo/chapter_1_vi.txt \
  --story-config configs/story.json \
  --metadata-provider deepseek \
  --background assets/setup_demo_background.jpg \
  --output-dir output/setup_demo/story_videos
```

Đây là một lượt gọi LLM riêng cho metadata; vẫn cần backend dịch đã đăng nhập/cấu hình. Thay `--metadata-provider openai` nếu dùng API đó. Với nhiều audio, lặp `--translated-file` đúng số lượng và đúng cặp audio/bản dịch theo thứ tự truyền vào.

Ngoài MP4/JPG/JSON render, sẽ có:

| File | Nội dung |
|---|---|
| `chapter_1.episode.json` | Kết quả metadata LLM, cache key và nguồn bản dịch |
| `chapter_1.youtube.json` | Metadata đã ghép, sẵn sàng upload; có thể biên tập trước upload |

Tiêu đề tự sinh dạng `Tên truyện | Điểm hấp dẫn của tập | Chương 1`. Title được rút gọn tối đa 100 ký tự; chữ thumbnail được giới hạn tối đa 8 từ/100 ký tự. Metadata chỉ được sinh lại khi cache không khớp hoặc bạn tắt resume; bản `.youtube.json` đã biên tập được giữ trong trường hợp cache vẫn hợp lệ.

### 11.5. Từ web đến video

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --background assets/setup_demo_background.jpg \
  --story-config configs/story.json \
  --chapters-per-video 1
```

Chưa có `--upload-youtube` nên chỉ tạo file local. `--story-config` ở lệnh `process` cần `--background` hoặc bật `--illustrate`; không dùng cùng `--youtube-metadata-file`.

## 12. Kết nối và upload YouTube

### 12.1. Chuẩn bị Google Cloud

1. Mở [Google Cloud Console](https://console.cloud.google.com/) và tạo/chọn project.
2. Bật **YouTube Data API v3** trong API Library.
3. Cấu hình màn hình đồng ý OAuth/Google Auth Platform. Nếu ứng dụng đang Testing, thêm tài khoản dùng đăng nhập vào Test users.
4. Tạo OAuth client loại **Desktop app**.
5. Tải JSON credentials và lưu tại `.secrets/youtube/client_secret.json` trong repo. Có thể đổi đường dẫn qua `.env`.

Luồng này sử dụng OAuth người dùng với trình duyệt và callback localhost. API key hoặc service account không thay cho tài khoản/kênh YouTube trong implementation này. Tham khảo [hướng dẫn OAuth Desktop của Google](https://developers.google.com/identity/protocols/oauth2/native-app).

```bash
mkdir -p .secrets/youtube
python -m pip install -r requirements-youtube.txt
```

Sau khi đã đặt JSON đúng chỗ:

```bash
python -m src.main youtube-auth
```

Chọn tài khoản/kênh và cấp quyền. Lệnh không upload video, chỉ lưu token và in channel ID. Điền **ID thực vừa được in ra** vào `.env`:

```ini
YOUTUBE_CLIENT_SECRETS_FILE=.secrets/youtube/client_secret.json
YOUTUBE_TOKEN_FILE=.secrets/youtube/token.json
YOUTUBE_CHANNEL_ID=DIEN_CHANNEL_ID_THAT
YOUTUBE_PRIVACY=private
YOUTUBE_CATEGORY_ID=22
```

Không dùng tên hiển thị kênh hoặc `@handle` thay ID. Khi upload, code đối chiếu kênh OAuth với ID bạn yêu cầu; không khớp thì dừng. Nếu Google thu hồi token hoặc refresh thất bại, đăng nhập lại bằng `youtube-auth`.

### 12.2. Xem trước metadata

Dùng video đã render ở phần 11:

```bash
python -m src.main youtube-upload output/setup_demo/videos/chapter_1.mp4 --dry-run
```

`--dry-run` đọc file và kiểm tra spec local; không đăng nhập hoặc upload. Nó không xác minh quota, quyền kênh hoặc khả năng YouTube chấp nhận video.

Với metadata theo truyện, chọn đúng video trong `output/setup_demo/story_videos/`; `.youtube.json` cùng tên được tự phát hiện.

Nếu muốn tự soạn toàn bộ metadata, tạo file JSON phẳng, ví dụ `configs/setup_demo_youtube.json`:

```json
{
  "title": "Truyện thử nghiệm | Chương 1",
  "description": "Nội dung thử nghiệm giọng đọc tiếng Việt.",
  "privacy": "private",
  "tags": ["truyện audio", "tiếng Việt"],
  "hashtags": ["TruyenAudio"],
  "category_id": "22",
  "default_language": "vi",
  "default_audio_language": "vi",
  "made_for_kids": false,
  "contains_synthetic_media": true,
  "notify_subscribers": false
}
```

```bash
python -m src.main youtube-upload output/setup_demo/videos/chapter_1.mp4 \
  --metadata-file configs/setup_demo_youtube.json --dry-run
```

`configs/youtube.example.json` minh họa dạng nhiều video: `defaults` + `videos`, key của `videos` là **tên file MP4**, không phải đường dẫn đầy đủ. Sửa tên key cho đúng video thực tế.

Thứ tự ưu tiên các giá trị title/description/privacy/tags đã hỗ trợ: tùy chọn CLI được truyền rõ → JSON upload được chọn → giá trị fallback của code/render/`.env`. Có `--metadata-file` thì file đó thay cho `.youtube.json` tự phát hiện, không tự ghép cả hai. Trong JSON nhiều video, mục video ghi đè `defaults`.

### 12.3. Upload thử ở chế độ riêng tư

Lệnh sau thực sự gửi video lên kênh:

```bash
python -m src.main youtube-upload output/setup_demo/videos/chapter_1.mp4 \
  --privacy private
python -m src.main youtube-status
```

Nếu đã dùng JSON thủ công ở bài dry-run, truyền lại cùng `--metadata-file` khi upload để dùng đúng nội dung vừa xem. Thumbnail JPG cùng tên được tự dùng nếu tồn tại. Với kênh chưa cho phép thumbnail tùy chỉnh, có thể thử `--no-thumbnail`, rồi xem cấu hình tính năng kênh trong Studio.

Sau upload, mở YouTube Studio để kiểm tra video, audio, metadata và trạng thái xử lý. Upload hoàn tất không đồng nghĩa YouTube đã encode xong hoặc video đã công khai.

### 12.4. Luồng đầy đủ có upload

Chỉ dùng sau khi các bước riêng đã chạy thành công:

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --background assets/setup_demo_background.jpg \
  --story-config configs/story.json \
  --upload-youtube --youtube-privacy private
```

`--upload-youtube` cần ảnh nền hoặc chế độ minh họa, channel ID và token đã có trước khi bắt đầu dịch. Muốn công khai sau khi đã upload private, chỉnh trong YouTube Studio. Chạy lại cùng video với `--privacy public` có thể bị chặn do metadata khác với checkpoint; lệnh upload không phải lệnh cập nhật video đã đăng.

### 12.5. Quy tắc metadata cần nhớ

- Mô tả được code giới hạn 5.000 **byte UTF-8**, không phải 5.000 ký tự tiếng Việt.
- Tags được kiểm tra tổng độ dài; hashtag không có dấu cách.
- JSON không cho key trùng hoặc trường không được hỗ trợ; boolean dùng `true`/`false`, không dùng chuỗi `"true"`.
- Nếu thêm `chapters` vào JSON upload, code yêu cầu ít nhất 3 mốc, bắt đầu 0, tăng cách nhau ít nhất 10 giây và mốc cuối nằm trong video. Không chép trực tiếp mảng `chapters` từ JSON render: schema hai nơi khác nhau.
- Nếu đặt `publish_at` trong JSON, dùng ISO 8601 có múi giờ và `privacy=private`. CLI chưa có cờ `--publish-at`; cách dễ vận hành lịch theo chương là Telegram ở phần 14.

## 13. Điều khiển qua Telegram

### 13.1. Token và quyền điều khiển

1. Tạo bot trong Telegram qua **@BotFather**, dùng `/newbot`.
2. Lấy token bot, lưu vào `.env` trên máy chạy project.
3. Xác định numeric user ID của tài khoản được điều khiển. Đây không phải username hoặc số điện thoại.

```ini
TELEGRAM_BOT_TOKEN=DIEN_TOKEN_BOT
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_PROGRESS_INTERVAL_SECONDS=30
```

Nhiều ID phân cách bằng dấu phẩy. Bot chỉ nhận chat riêng của các ID được phép; không nhận lệnh group/channel.

Nếu chưa biết ID, dừng mọi tiến trình đang polling bot, gửi `/start` trong chat riêng với bot rồi chạy đoạn đọc ID sau từ root. Đoạn này chỉ in ID/tên, không in token:

```bash
python - <<'PY'
import logging
import httpx
from src import config
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
if not config.TELEGRAM_BOT_TOKEN:
    raise SystemExit('Điền TELEGRAM_BOT_TOKEN trong .env trước.')
try:
    response = httpx.post(
        f'https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates',
        json={'timeout': 0, 'allowed_updates': ['message']}, timeout=15)
    data = response.json()
except Exception:
    raise SystemExit('Không đọc được Telegram; kiểm tra mạng/token.') from None
if not data.get('ok'):
    raise SystemExit(f"Telegram từ chối yêu cầu; mã {data.get('error_code', 'unknown')}.")
seen = set()
for update in data.get('result', []):
    message = update.get('message', {})
    user = message.get('from', {})
    if message.get('chat', {}).get('type') == 'private' and user.get('id') not in seen:
        seen.add(user.get('id'))
        print('User ID:', user.get('id'), '| Tên:', user.get('first_name', ''))
if not seen:
    print('Chưa có tin nhắn mới; gửi lại /start rồi thử lại.')
PY
```

Chọn đúng ID của bạn trong kết quả, điền vào `.env`. Không chạy đoạn lấy ID song song với bot đang chạy. Cách đọc `message.from.id` được định nghĩa trong [Telegram Bot API](https://core.telegram.org/bots/api#message).

### 13.2. Tạo profile truyện

Nếu chưa có cấu hình cá nhân:

```bash
cp -n configs/telegram.example.json configs/telegram.json
```

Chỉnh profile ví dụ:

```json
{
  "stories": {
    "wallstreet": {
      "chapter_url_template": "https://ixdzs8.com/read/644938/p{chapter}.html",
      "story_config": "story.json",
      "background": "../assets/setup_demo_background.jpg",
      "glossary": "../input/web/ixdzs8/644938/glossary.csv",
      "translation_provider": "deepseek",
      "translation_model": "deepseek-chat",
      "tts_provider": "vieneu",
      "upload_youtube": false,
      "youtube_privacy": "private",
      "daily_publish_times": ["06:30", "11:30", "17:00", "19:30", "22:00"]
    }
  }
}
```

Đầu tiên dùng `upload_youtube=false` để kiểm tra chỉ tạo video. Chuyển sang `true` sau khi OAuth và upload thử đã ổn.

- `wallstreet` là ID truyện bạn nhập trong Telegram; đặt 1–40 ký tự chữ/số/`_`/`-`.
- Template cần đúng một biến `{chapter}` và URL phải là nguồn đang hỗ trợ.
- `story_config` và `background` phải tồn tại; glossary có thể chưa tồn tại, hệ thống có thể tạo khi học thuật ngữ.
- Bot luôn dùng story config để tạo metadata, kể cả khi tắt upload; vẫn cần backend LLM hoạt động.
- Profile chọn provider/model dịch; giọng đọc và nhiều cấu hình khác lấy từ `.env` của máy. Schema profile chưa có trường voice riêng cho từng truyện.
- Mỗi job bot luôn là **một chương → một video**, không dùng số chương/video global để gom job.

### 13.3. Kiểm tra profile trước khi chạy

```bash
python -m json.tool configs/telegram.json > /dev/null
python -m json.tool configs/story.json > /dev/null
python - <<'PY'
from src.remote.profiles import load_profiles
profiles = load_profiles('configs/telegram.json')
print('Profile hợp lệ:', ', '.join(profiles))
PY
```

Bước này kiểm tra cấu trúc/đường dẫn/provider, không dịch, không gửi Telegram, không upload.

### 13.4. Khởi động bot

```bash
python -m src.main telegram-bot --profiles configs/telegram.json
```

Trên macOS để giữ máy thức khi bot chạy:

```bash
caffeinate -i python -m src.main telegram-bot --profiles configs/telegram.json
```

Mở chat riêng và gửi:

```text
/menu
/stories
/run wallstreet 1
/status
```

Menu hỗ trợ chọn truyện, nhập chương, xem lại và xác nhận. `/abort` bỏ thao tác đang nhập. Với lệnh đầy đủ như `/run wallstreet 1`, bot thực hiện trực tiếp, không qua bước xác nhận của menu.

Bot dùng long polling; không cần mở cổng/router hoặc chạy server Telegram. Chỉ chạy một tiến trình dùng token đó. Có một worker xử lý pipeline tuần tự; phần nhận lệnh/status vẫn hoạt động trong khi job chạy.

Máy cần bật, có mạng và bot đang chạy để nhận lệnh/bắt đầu job. Đóng Terminal có thể dừng bot; `caffeinate` giữ thức nhưng không tự khởi động sau reboot. Nếu dùng phiên Terminal dài hạn trên Linux có thể chạy trong `tmux`; repo chưa kèm cấu hình dịch vụ tự khởi động.

### 13.5. Lệnh thường dùng

| Lệnh | Tác dụng |
|---|---|
| `/menu` | Mở bảng điều khiển |
| `/new` | Luồng chạy/hẹn giờ một chương |
| `/plan` | Luồng lịch 5 chương/ngày |
| `/run wallstreet 1` | Xếp hàng chương 1 ngay |
| `/status` | Danh sách job |
| `/status page 2` | Trang tiếp theo |
| `/status 12` | Chi tiết job ID 12 |
| `/cancel 12 13` | Hủy các job đang chờ |
| `/retry 12` | Thử lại job lỗi/bị ngắt, giữ lịch cũ |
| `/clear finished` | Ẩn lịch sử hoàn thành/đã hủy |
| `/clear failed` | Ẩn lịch sử lỗi/bị ngắt |
| `/abort` | Thoát bản nháp đang nhập |

Số trong `/status`, `/retry`, `/cancel` là **ID job**, không phải số chương. `/cancel` không dừng job đang chạy. `/clear` không xóa file hoặc video YouTube và không bỏ dấu vết chống upload trùng.

## 14. Lên lịch công khai

### 14.1. Hẹn giờ bắt đầu xử lý

```text
/schedule wallstreet 2 2026-11-10 09:00
```

Đây là **09:00 ngày 10/11/2026 giờ Việt Nam bắt đầu pipeline**, không phải giờ YouTube công khai. Nếu worker bận thì job đợi. Khi đọc guide vào ngày muộn hơn, thay bằng một ngày giờ tương lai.

### 14.2. Hẹn 5 chương/ngày trên YouTube

Yêu cầu profile bật `upload_youtube=true` và OAuth đã sẵn sàng:

```text
/schedule-day wallstreet 10 2026-11-10 3
```

Ví dụ tạo 15 job cho chương 10–24 trong 3 ngày. Mỗi lệnh hỗ trợ 1–7 ngày; không phải lịch lặp vô hạn.

Năm mốc mặc định theo `Asia/Ho_Chi_Minh`:

| Chương của ngày đầu | Giờ công khai |
|---|---|
| 10 | 06:30 |
| 11 | 11:30 |
| 12 | 17:00 |
| 13 | 19:30 |
| 14 | 22:00 |

Bot cho job sẵn sàng trong cửa sổ 24 giờ trước từng giờ công khai; upload private và gửi `publishAt` cho YouTube. Đây là thời điểm sớm nhất được xếp xử lý, không bảo đảm bắt đầu đúng lúc hoặc kịp publish nếu máy/mạng chậm.

`daily_publish_times` cần đúng 5 mốc khác nhau, tăng dần theo `HH:MM`. Nếu có mốc đã qua hoặc chương xung đột với job đã có, lệnh bị từ chối thay vì tạo một phần batch. Chỉnh profile rồi restart bot để áp dụng cho job mới; job đã tạo giữ bản cấu hình được chụp lúc enqueue.

### 14.3. Lỡ giờ hoặc cần chạy ngay

Đặt lại giờ công khai cho job lỗi/bị ngắt:

```text
/retry 12 2026-11-11 19:30
```

Giờ mới phải ở tương lai hơn 15 phút, và nên dư thời gian cho dịch/TTS/render/upload. Nếu video đã upload hoặc trạng thái phiên cũ không xác định, kiểm tra/đổi lịch trong YouTube Studio; bot không tự tạo bản trùng.

Chạy/retry ngay bằng:

```text
/now 12
```

Lệnh này giữ checkpoint và ưu tiên job sau job đang chạy, bỏ lịch chờ/cửa sổ chuẩn bị/cooldown upload nội bộ, đồng thời bỏ lịch công khai: video được upload **private, không hẹn công khai**. Giới hạn gọi DeepSeek vẫn giữ; YouTube vẫn có thể từ chối do hạn mức thật. Đây khác `/run`, vốn tạo/chọn job theo profile và đi theo hàng đợi thông thường.

## 15. Vận hành, khôi phục và sao lưu

### 15.1. State nằm ở đâu?

| Đường dẫn mặc định | Nội dung |
|---|---|
| `output/.state/jobs.sqlite3` | Job TTS và trạng thái đoạn |
| `output/.state/chunks/` | Chunk audio để tiếp tục/tái sử dụng |
| `output/.state/last_batch_report.json` | Tổng kết batch TTS gần nhất |
| `output/.state/video/videos.sqlite3` | Checkpoint render video |
| `output/.state/youtube/uploads.sqlite3` | Phiên upload, offset, video ID và chống tải trùng |
| `output/.state/telegram/bot.sqlite3` | Job bot, lịch, quyền sở hữu, tiến độ, bản nháp menu |
| `output/.state/telegram/artifacts/<job_id>/artifacts.json` | Manifest đường dẫn/hash theo bước của job bot |
| `output/.state/deepseek_requests/` | Lịch sử và cooldown lượt gọi DeepSeek |
| `<glossary>.csv.sqlite3` | Bằng chứng/ứng viên thuật ngữ của glossary đó |
| `.secrets/youtube/` | OAuth client JSON và token |
| `infra/Deepseek-API/session/` | Session/profile DeepSeek |

`tts --state-dir` chỉ chuyển state TTS cho lệnh đó. `telegram-bot --state-dir` chỉ chuyển database/manifest bot, không tự chuyển mọi cache TTS/video/YouTube/DeepSeek. YouTube và DeepSeek có biến cấu hình state riêng.

### 15.2. Khi tiến trình bị ngắt

- TTS CLI: chạy lại cùng lệnh; không xóa chunk/state.
- Render: chạy lại cùng lệnh; video hoàn chỉnh được kiểm tra lại, render dở có thể phải làm lại cả video đó, không resume từng frame.
- Upload CLI: chạy lại cùng video và metadata; giữ nguyên database upload.
- Bot restart: job đang chạy khi bị chết được đánh dấu `interrupted`, không tự tiếp tục ngay; gửi `/retry <id>` hoặc thao tác qua menu.
- Ctrl+C khi bot đang chạy sẽ ngừng polling và **chờ job hiện tại xong**, không phải hủy ngay job đó.
- Nếu bot báo artifact bị sửa/xóa, kiểm tra/khôi phục file gốc. Không xóa manifest/database để ép chạy lại, nhất là khi đã có upload.

Không chạy CLI và bot cùng sửa/chạy một chương khi worker đang xử lý. File lock bảo vệ một số state nhưng không biến các lệnh trùng đầu ra thành luồng an toàn để chạy song song.

### 15.3. Sao lưu và chuyển máy

Dừng bot và các lệnh ghi file, đợi job kết thúc trước khi copy. Sao lưu:

1. Mã nguồn cùng revision submodule, `.env`, JSON cấu hình và ảnh/font bạn dùng.
2. `input/`, glossary CSV **và database glossary**.
3. Toàn bộ `output/`, gồm cả thư mục ẩn `.state` và các sidecar JSON/JPG.
4. Model local hoặc thông tin để tải lại model đúng phiên bản.
5. Credentials/session cần thiết nếu chuyển máy, lưu trong bản backup riêng tư; có thể chọn đăng nhập lại trên máy mới.

Manifest/cache có lưu đường dẫn tuyệt đối. Khi chuyển sang vị trí khác, không giả định mọi checkpoint sẽ tiếp tục dùng được nguyên trạng. Giữ bản sao đầy đủ, kiểm tra artifact và trạng thái YouTube trước khi retry. Không xóa database upload để giải quyết lỗi di chuyển đường dẫn.

Có thể ghi lại môi trường đang chạy ổn bằng:

```bash
python --version
python -m pip freeze > requirements-local-snapshot.txt
```

Nếu dùng venv của uv không có pip, thay bằng `uv pip freeze --python .venv/bin/python`. File snapshot là ghi nhận môi trường cục bộ, chưa phải lockfile đã kiểm chứng trên mọi máy.

### 15.4. Nhật ký dài hạn

```bash
mkdir -p output/logs
python -m src.main telegram-bot --profiles configs/telegram.json \
  >> output/logs/telegram.log 2>&1
```

Mở Terminal khác để xem:

```bash
tail -f output/logs/telegram.log
```

Log tăng dần; theo dõi dung lượng và tự xoay vòng khi chạy lâu. Không công khai `.env`, `.secrets/`, session DeepSeek hoặc database upload có URL phiên upload. Chỉ chia sẻ log sau khi kiểm tra dữ liệu nhạy cảm.

## 16. Tra cứu cấu hình

Giá trị dưới đây là mặc định trong `src/config.py` hoặc giá trị khởi đầu được đề xuất rõ trong guide; `.env` hiện có của bạn có thể khác.

### 16.1. Dịch và glossary

| Biến | Mặc định code | Ghi chú |
|---|---|---|
| `TRANSLATION_PROVIDER` | `openai` | `openai` / `deepseek` |
| `OPENAI_API_KEY` | Rỗng | Dùng cho dịch OpenAI và OpenAI TTS |
| `OPENAI_BASE_URL` | `None` nếu không khai báo | Guide đặt URL rõ; tránh chuỗi rỗng |
| `TRANSLATION_MODEL` | `gpt-4o-mini` | Model nhánh OpenAI |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Hoặc `deepseek-expert` |
| `DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION` | `5` | Số đoạn, không phải số chương; >= 1 |
| `GLOSSARY_AUTO_UPDATE` | `true` | Guide tắt khi test dịch ban đầu |
| `GLOSSARY_MIN_OCCURRENCES` | `3` | Bằng chứng xuất hiện thuật ngữ |
| `GLOSSARY_MIN_DISTINCT_CHUNKS` | `2` | Số đoạn gốc khác nhau |
| `GLOSSARY_MAX_AUTO_ENTRIES` | `500` | Giới hạn entry tự thêm |
| `GLOSSARY_MAX_PROMPT_ENTRIES` | `100` | Entry được chọn cho prompt khi học bật |
| `GLOSSARY_MAX_CANDIDATES` | `2000` | Giới hạn ứng viên |
| `METADATA_MAX_INPUT_CHARS` | `60000` | Tổng ký tự bản dịch cho một lượt metadata |

### 16.2. TTS

| Biến | Mặc định code | Ghi chú |
|---|---|---|
| `TTS_PROVIDER` | `edge-tts` | Mẫu `.env.example` lại chọn Piper |
| `TTS_VOICE` | `vi-VN-HoaiMyNeural` | Factory dùng cho Edge |
| `TTS_RATE` | `+0%` | Edge; ví dụ `+10%`, `-5%` |
| `TTS_VOLUME` | `+0%` | Edge |
| `TTS_PITCH` | `+0Hz` | Edge |
| `MAX_CHUNK_CHARS` | `2000` | Kích thước đoạn TTS |
| `TTS_CONCURRENCY` | `3` | Kích thước batch/số tác vụ theo provider |
| `PIPER_MODEL_PATH` | `models/piper/vi_VN-vais1000-medium.onnx` | Cần tải model |
| `PIPER_CONFIG_PATH` | Đường dẫn model + `.json` | Cần đúng cặp |
| `PIPER_NUM_WORKERS` | `4` | Batch pipeline vẫn truyền concurrency riêng |
| `VIENEU_MODE` | `v3turbo` | Bắt đầu với mode này |
| `VIENEU_VOICE` | `None` khi không khai báo | Để trống dùng mặc định |
| `VIENEU_BACKBONE_REPO` | Không khai báo | Chỉ đặt khi dùng model cụ thể |
| `VIENEU_BACKBONE_DEVICE` | `cpu` | Tùy mode/SDK |
| `VIENEU_PRECISION` | Không khai báo | Chỉ đặt giá trị SDK/mode hỗ trợ |
| `VIENEU_CODEC_REPO` | Không khai báo | Tùy model |
| `VIENEU_CODEC_DEVICE` | `cpu` | Tùy mode/SDK |
| `VIENEU_API_BASE` | Không khai báo | Bắt buộc ở remote mode |
| `VIENEU_MODEL_NAME` | Không khai báo | Bắt buộc ở remote mode |
| `HF_TOKEN` | Không khai báo | Khi model yêu cầu |

`PAUSE_BETWEEN_CHUNKS_MS` có trong config, mặc định 300, nhưng runner/merger hiện không dùng để chèn khoảng nghỉ. Thay biến này chưa tạo khoảng lặng giữa các chunk.

### 16.3. Video, YouTube và Telegram

| Biến | Mặc định code | Ghi chú |
|---|---|---|
| `VIDEO_CHAPTERS_PER_VIDEO` | `1` | Bot vẫn cố định 1 chương/video |
| `VIDEO_WIDTH`, `VIDEO_HEIGHT` | `1920`, `1080` | Số chẵn >= 16 |
| `VIDEO_FPS` | `30` | 1–60 |
| `VIDEO_FONT_PATH` | Không khai báo | Font TTF/OTF |
| `YOUTUBE_CLIENT_SECRETS_FILE` | `.secrets/youtube/client_secret.json` ở root | OAuth Desktop JSON |
| `YOUTUBE_TOKEN_FILE` | `.secrets/youtube/token.json` ở root | Token tạo bởi `youtube-auth` |
| `YOUTUBE_CHANNEL_ID` | Rỗng | ID kênh OAuth |
| `YOUTUBE_PRIVACY` | `private` | JSON/CLI có thể ghi đè |
| `YOUTUBE_CATEGORY_ID` | `22` | Category ID dạng chuỗi số |
| `YOUTUBE_STATE_DIR` | `output/.state/youtube` ở root | Giữ để resume/chống trùng |
| `TELEGRAM_BOT_TOKEN` | Rỗng | Lấy qua BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | Rỗng | ID số dương, phân cách dấu phẩy |
| `TELEGRAM_PROGRESS_INTERVAL_SECONDS` | `30` | Bot áp dụng tối thiểu 10 giây |

Các biến pacing DeepSeek và `DEEPSEEK_REQUEST_STATE_DIR` được giải thích ở phần 8.5. Các cấu hình số được đọc khi import module; chuỗi rỗng/không phải số có thể làm ngay cả `--help` lỗi. Sau khi đổi `.env`, khởi động lại bot.

## 17. Xử lý lỗi

| Triệu chứng | Kiểm tra và cách xử lý |
|---|---|
| `No module named src` | Vào thư mục gốc, dùng `python -m src.main`, kích hoạt đúng venv |
| `No module named pip` | Với venv uv, dùng `uv pip install --python .venv/bin/python ...` |
| Thiếu module `openai`, `typer`, `dotenv`, `PIL` | Cài requirements trong đúng môi trường; `PIL` đến từ gói `Pillow` |
| Không tìm thấy `ffmpeg`/`ffprobe` | Cài FFmpeg, mở Terminal mới; kiểm tra cả hai chương trình trong PATH |
| `No module named fcntl` | Đang chạy Windows native; chuyển sang Linux/WSL2 |
| Sao chép `.env.example` xong bị lỗi model | Mẫu chọn Piper; đổi provider hoặc cài/tải đủ Piper |
| `Không tìm thấy model Piper` | Kiểm tra hai file model/JSON và thư mục đang chạy; không có `scripts/setup_piper.sh` |
| Piper lỗi `synthesize` / `audio_int16_bytes` | Kiểm tra phiên bản Piper tương thích API adapter; thử một đoạn trước batch |
| VieNeu import/nạp model thất bại | Giữ bản 3.8.3, kiểm tra dependency, mạng, dung lượng, quyền model; chạy với CPU và giọng mặc định |
| Không có giọng VieNeu đã điền | Xóa `VIENEU_VOICE` để thử mặc định; `voices` chỉ là bảng Edge |
| Edge-TTS không trả audio | Kiểm tra mạng/VPN/proxy, thử đoạn ngắn và `--concurrency 1`; chưa thể kết luận chỉ từ `doctor` |
| OpenAI thiếu key / 401 | Điền key đúng, kiểm tra biến export và endpoint |
| OpenAI URL lỗi | Không để `OPENAI_BASE_URL` rỗng; dùng URL đầy đủ đúng backend |
| OpenAI không có model / quota | Dùng model tài khoản hỗ trợ; kiểm tra quyền/quota tại nhà cung cấp |
| DeepSeek client không tồn tại | `git submodule update --init --recursive` |
| DeepSeek thiếu dependency/browser | Cài `requirements-deepseek.txt` và `python -m playwright install chromium` |
| DeepSeek cần đăng nhập | Vào `infra/Deepseek-API`, chạy `python -m deepseek.auth`, rồi về root |
| DeepSeek chờ nhiều giây/phút | Xem pacing/cooldown; glossary/metadata cũng dùng lượt gọi chung |
| State DeepSeek báo hỏng | Dừng các process liên quan, giữ bản sao, kiểm tra/khôi phục state hợp lệ; không reset mù để bỏ giới hạn |
| Không tìm thấy nội dung web | Kiểm tra URL chương HTTPS đúng dạng; website có thể chặn hoặc đổi HTML |
| Không thấy TXT trong thư mục | CLI chỉ lấy `*.txt` trực tiếp, không đệ quy |
| File TXT rỗng | Điền nội dung; `generate_files.py` chỉ tạo file trống |
| Glossary CSV lỗi | Đúng hai cột, đúng quoting; tách glossary theo truyện |
| `--story-config` thiếu đầu vào hình ảnh | Truyền `--background` hoặc bật `--illustrate` với bridge Gemini đã cấu hình |
| Render có audio nhưng chữ lỗi | Chọn font có tiếng Việt, kiểm tra `VIDEO_FONT_PATH` |
| Video sai kích thước/fps | Kích thước chẵn >= 16, fps 1–60; kiểm tra giá trị `.env` |
| Metadata vượt độ dài đầu vào | Giảm số chương/video hoặc chỉnh `METADATA_MAX_INPUT_CHARS` phù hợp backend |
| OAuth JSON không tìm thấy | Đặt đúng Desktop client JSON theo `YOUTUBE_CLIENT_SECRETS_FILE` |
| Google `access_denied`/token hết hạn | Kiểm tra tài khoản test, quyền OAuth và cấu hình ứng dụng; đăng nhập lại khi cần |
| Kênh OAuth không khớp | Chạy `youtube-auth`, chọn đúng kênh, cập nhật ID thực |
| Thumbnail upload lỗi | Kiểm tra JPG/PNG <= 2 MiB và quyền tính năng kênh; thử lại với `--no-thumbnail` |
| Video đã upload nhưng thumbnail lỗi | Giữ checkpoint và retry; code có thể tiếp tục thumbnail, không cần tải lại video |
| `uploadLimitExceeded` | Bot giữ các job upload trong 24 giờ; retry job cũ khi phù hợp, chỉnh lịch tương lai nếu cần |
| Upload báo metadata khác | Giữ metadata cũ hoặc chỉnh video trong Studio; không xóa state để upload trùng |
| Phiên upload hết hạn/không rõ kết quả | Kiểm tra YouTube Studio trước; code không tự tạo lại phiên mơ hồ |
| Đã lỡ giờ publish | `/retry <id> YYYY-MM-DD HH:MM` với giờ tương lai; nếu đã upload, đổi trong Studio |
| Bot không trả lời | Tiến trình còn chạy, token đúng, đúng numeric allowed ID, gửi chat riêng, kiểm tra mạng |
| Telegram HTTP 409 | Có process polling thứ hai hoặc webhook cũ; dừng process trùng, kiểm tra cấu hình webhook |
| Bot báo profile không hợp lệ | Đường dẫn tính từ JSON; ảnh/story config phải có; template đúng một `{chapter}` |
| Bot báo đã có job chương đó | Xem lại job cũ; `/retry` job lỗi thay vì tạo job trùng |
| Nút Telegram đã cũ/hết hạn | Mở `/menu`; bản nháp hết hạn sau 30 phút không cập nhật |
| Job bị `interrupted` sau restart | Mở chi tiết và retry; bot không tự chạy lại job dở |
| Artifact đã bị sửa/xóa | Khôi phục/kiểm tra file được manifest tham chiếu; giữ state chống tải trùng |
| File lock đang được dùng | Đợi tiến trình đang chạy kết thúc; đừng xóa file lock để vượt qua process còn sống |
| Chỉnh `.env` không có tác dụng | Restart process, kiểm tra biến môi trường đã export, tránh dòng biến trùng |

## 18. Kiểm tra hoàn tất và nguồn tham khảo

### 18.1. Checklist theo từng mốc

- [ ] Python trong đúng venv, phiên bản 3.12.
- [ ] `ffmpeg -version` và `ffprobe -version` chạy được.
- [ ] `python -m src.main --help` hiển thị danh sách lệnh.
- [ ] `doctor` đạt cho provider đã chọn.
- [ ] Tạo được MP3 mẫu và nghe có tiếng Việt.
- [ ] Nếu cần dịch: dịch được đoạn mẫu, đọc lại bản dịch.
- [ ] Nếu dùng web: `fetch` lưu được TXT/JSON đúng chương.
- [ ] Render được MP4/JPG/JSON, mở video kiểm tra tiếng/hình/chữ.
- [ ] Nếu cần metadata: tạo/kiểm tra `.youtube.json`.
- [ ] Nếu upload: OAuth đúng kênh, dry-run hợp lệ, thử upload private thành công.
- [ ] Nếu dùng bot: `/menu`, `/stories`, một job chỉ tạo video chạy thành công.
- [ ] Sau đó mới bật upload và thử lịch với ngày giờ tương lai.
- [ ] Giữ backup input, glossary, output, state và cấu hình.

### 18.2. Kiểm thử tự động

```bash
python -m unittest discover -s tests -v
```

Khi rà soát hướng dẫn này, bộ kiểm thử hiện có chạy **193 test, tất cả đạt**, trong môi trường Python 3.12.14 trên máy hiện tại, với FFmpeg/ffprobe. `doctor --provider edge-tts` và `doctor --provider vieneu` cũng đạt.

Test dùng dịch vụ LLM/TTS/Telegram/YouTube mô phỏng và media FFmpeg thật ở các bài liên quan. Kết quả này **không xác nhận** key/session/quota còn hợp lệ, tải model mới thành công, TTS thật hoạt động, bot gửi tin nhắn thật hoặc upload thật trên tài khoản của bạn. Lần rà soát này không cài lại môi trường sạch và không chạy giao dịch dịch/upload thật.

### 18.3. Nguồn đối chiếu

Hành vi ứng dụng trong guide được đối chiếu với `src/`, cấu hình mẫu, requirements và bộ test trong repo; mã nguồn hiện tại được ưu tiên khi README/roadmap khác nhau.

Tài liệu bên ngoài cho bước tích hợp:

- [VieNeu-TTS upstream](https://github.com/pnnbao97/VieNeu-TTS): tài liệu mới có thể khác SDK 3.8.3 mà project ghim.
- [Piper Python API và cài đặt](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).
- [Hai file model Piper tiếng Việt](https://huggingface.co/rhasspy/piper-voices/tree/main/vi/vi_VN/vais1000/medium).
- [Google OAuth cho ứng dụng Desktop](https://developers.google.com/identity/protocols/oauth2/native-app).
- [Telegram Bot API — Message](https://core.telegram.org/bots/api#message).

Để tra tùy chọn đúng bản đang chạy, dùng `python -m src.main <tên-lệnh> --help`. Tất cả ví dụ có ngày giờ cố định cần đổi sang tương lai trước khi dùng.
