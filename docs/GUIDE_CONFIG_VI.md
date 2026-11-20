# Hướng dẫn cấu hình lần chạy

File JSON cho phép lưu toàn bộ tham số của một lần chạy để không phải nhập câu
lệnh dài. Dự án hiện hỗ trợ file cấu hình cho hai lệnh:

- `process`: dịch tiếng Anh sang tiếng Việt rồi tạo audio.
- `tts`: chuyển một hoặc nhiều file tiếng Việt đã có sang audio.

## Chuẩn bị

Mở Terminal tại thư mục gốc của dự án, kích hoạt môi trường Python:

```bash
cd /home/himakevolution/Documents/Working/Project/novel2voice
source .venv/bin/activate
```

Tạo file cấu hình riêng từ mẫu:

```bash
# Luồng dịch + TTS
cp -n configs/process.example.json configs/process.json

# Luồng chỉ TTS
cp -n configs/tts.example.json configs/tts.json
```

Nên giữ các file `*.example.json` làm mẫu và đặt cấu hình cá nhân trong
`configs/*.json`. Đường dẫn trong JSON thường được tính từ thư mục gốc của dự án.

## Chạy bằng file cấu hình

```bash
# Dịch và tạo audio
python -m src.main process --config configs/process.json

# Chỉ tạo audio từ file hoặc thư mục tiếng Việt
python -m src.main tts --config configs/tts.json
```

Tham số truyền trực tiếp bằng CLI sẽ ghi đè giá trị trong file JSON:

```bash
python -m src.main process --config configs/process.json \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural
```

Với cấu hình sai hoặc thiếu dữ kiện bắt buộc, chương trình sẽ báo lỗi. Trường
`command` trong JSON phải khớp với lệnh đang chạy.

## Cấu hình `process`

Mẫu đầy đủ nằm tại [configs/process.example.json](../configs/process.example.json).

```json
{
  "command": "process",
  "input_path": "input/my_story/chapter_1.txt",
  "translation_provider": "deepseek",
  "model": "deepseek-chat",
  "provider": "vieneu",
  "voice": "Ngọc Lan",
  "rate": "+0%",
  "glossary_path": "glossary.csv",
  "cleanup_temp": true,
  "concurrency": 3,
  "max_chapters": 1,
  "output_audio": "output/chapter_1.mp3",
  "background": null,
  "video_title": "",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false
}
```

### Các tham số chính

| Khóa | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `command` | chuỗi | Phải là `"process"` để file chỉ dùng cho lệnh này. |
| `input_path` | chuỗi | Bắt buộc. Đường dẫn file TXT, thư mục TXT hoặc URL chương. |
| `translation_provider` | chuỗi | Backend dịch: `openai` hoặc `deepseek`. |
| `model` | chuỗi hoặc `null` | Model dùng cho dịch thuật, ví dụ `gpt-4o-mini` hoặc `deepseek-chat`. |
| `provider` | chuỗi | Backend đọc TTS: `vieneu`, `piper`, `edge-tts` hoặc `openai`. |
| `voice` | chuỗi hoặc `null` | Giọng đọc của provider TTS đang chọn. Voice ID không dùng chung giữa các provider. |
| `rate` | chuỗi | Tốc độ đọc, ví dụ `"+0%"`, `"+10%"` hoặc `"-5%"`. Chủ yếu dùng với Edge-TTS. |
| `glossary_path` | chuỗi hoặc `null` | File CSV chuẩn hóa tên riêng và thuật ngữ truyện. |
| `cleanup_temp` | boolean | `true` xóa các đoạn audio tạm sau ghép; `false` giữ lại để sửa lỗi. |
| `concurrency` | số nguyên | Số đoạn/chương TTS xử lý song song. Giá trị nhỏ giúp tránh quá tải API hoặc GPU. |
| `max_chapters` | số nguyên | Số chương tối đa khi `input_path` là URL; thường là `1` trở lên. |
| `output_audio` | chuỗi hoặc `null` | Đường dẫn MP3 đầu ra cho một file. Với thư mục hoặc batch, để `null`. |

### Các tham số video và YouTube

| Khóa | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `background` | chuỗi hoặc `null` | Ảnh nền tĩnh để render video. Không để `null` nếu cần render video. |
| `story_config` | chuỗi hoặc `null` | File JSON metadata của truyện, ví dụ `configs/story.json`. |
| `video_title` | chuỗi | Tiêu đề xuất hiện trong video. |
| `video_output_dir` | chuỗi | Thư mục lưu MP4 và thumbnail. |
| `chapters_per_video` | số nguyên | Số chương ghép thành một video. Mặc định là `1`. |
| `upload_youtube` | boolean | `true` upload sau khi render; cần đăng nhập OAuth và cấu hình kênh YouTube. |
| `youtube_metadata_file` | chuỗi hoặc `null` | File JSON metadata YouTube tùy chỉnh. Không dùng đồng thời với `story_config`. |
| `youtube_privacy` | chuỗi hoặc `null` | Quyền riêng tư upload: `private`, `unlisted` hoặc `public`. |

Ví dụ render video nhưng không upload:

```json
{
  "command": "process",
  "input_path": "input/my_story/chapter_1.txt",
  "provider": "vieneu",
  "translation_provider": "deepseek",
  "background": "input/backgrounds/background.jpg",
  "story_config": "configs/story.json",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false
}
```

## Cấu hình `tts`

Mẫu đầy đủ nằm tại [configs/tts.example.json](../configs/tts.example.json).

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

| Khóa | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `command` | chuỗi | Phải là `"tts"` để file chỉ dùng cho lệnh này. |
| `vi_path` | chuỗi | Bắt buộc. File TXT tiếng Việt hoặc thư mục chứa các file `.txt`. |
| `output_audio` | chuỗi hoặc `null` | File MP3 đầu ra khi `vi_path` là một file. |
| `provider` | chuỗi | Backend TTS: `vieneu`, `piper`, `edge-tts` hoặc `openai`. |
| `voice` | chuỗi hoặc `null` | Giọng đọc tương ứng với provider. |
| `rate` | chuỗi | Tốc độ đọc, chủ yếu dùng với Edge-TTS. |
| `cleanup_temp` | boolean | Xóa hoặc giữ đoạn audio tạm sau khi ghép. |
| `combine` | boolean | `true` ghép toàn bộ thư mục thành một MP3; vẫn giữ các MP3 riêng từng chương. |
| `concurrency` | số nguyên | Số luồng xử lý song song. |
| `resume` | boolean | `true` tái sử dụng kết quả hợp lệ đã tạo để chạy nhanh hơn. |
| `state_dir` | chuỗi | Thư mục lưu checkpoint SQLite và audio tạm. |
| `retries` | số nguyên | Số lần thử lại một đoạn/chương sau khi TTS lỗi. |
| `continue_on_error` | boolean | `true` tiếp tục các chương khác khi một chương lỗi; `false` dừng ngay. |
| `background` | chuỗi hoặc `null` | Ảnh nền; đặt giá trị này để render video ngay sau TTS. |
| `story_config` | chuỗi hoặc `null` | JSON metadata truyện cho tiêu đề/mô tả/thumbnail; không dùng cùng `youtube_metadata_file`. |
| `video_title` | chuỗi | Tiêu đề nền tảng cho tập video. |
| `video_output_dir` | chuỗi | Thư mục lưu MP4, thumbnail và metadata video. |
| `chapters_per_video` | số nguyên | Số chương ghép thành một video. |
| `upload_youtube` | boolean | `true` upload video sau render; cần OAuth/channel đã cấu hình. |
| `youtube_metadata_file` | chuỗi hoặc `null` | JSON metadata YouTube tùy chỉnh thay cho `story_config`. |
| `youtube_privacy` | chuỗi | Quyền riêng tư upload: `private`, `unlisted` hoặc `public`. |
| `dry_run` | boolean | `true` chỉ kiểm tra input/kế hoạch; không chạy TTS, FFmpeg, OAuth hoặc ghi output/state. |

### TXT đã dịch sẵn hoặc văn học tiếng Việt

Lệnh `tts` không chạy dịch thuật. Nó nhận trực tiếp file hoặc thư mục `.txt`
tiếng Việt, tạo MP3 và có thể tiếp tục render video trong cùng một lần chạy:

```json
{
  "command": "tts",
  "vi_path": "input/hai_dua_tre",
  "provider": "edge-tts",
  "voice": "vi-VN-HoaiMyNeural",
  "combine": true,
  "cleanup_temp": true,
  "resume": true,
  "background": "assets/background.jpg",
  "story_config": "configs/story.json",
  "video_title": "Hai đứa trẻ",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false
}
```

Chạy:

```bash
python -m src.main tts --config configs/tts.json
```

### Dry run

Kiểm tra cấu hình TTS/video mà không tạo media hoặc thay đổi state:

```bash
python -m src.main tts --config configs/vietnamese.json --dry-run
```

Hoặc bật trực tiếp trong JSON:

```json
{
  "command": "tts",
  "vi_path": "input/hai_dua_tre",
  "dry_run": true
}
```

## Tùy chọn provider

`translation_provider` điều khiển bước dịch, còn `provider` điều khiển bước đọc.
Đây là hai loại provider khác nhau.

| Provider dịch | Yêu cầu |
|---|---|
| `openai` | Cấu hình `OPENAI_API_KEY`, `OPENAI_BASE_URL` nếu dùng máy chủ tương thích, và `TRANSLATION_MODEL`. |
| `deepseek` | Cấu hình dịch vụ/credential DeepSeek theo hướng dẫn trong `.env.example`. |

| Provider TTS | Cách hoạt động | Cần lưu ý |
|---|---|---|
| `edge-tts` | Dùng dịch vụ Edge-TTS | Cần mạng; giọng ví dụ `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`. |
| `openai` | Gọi API OpenAI | Cần `OPENAI_API_KEY`; giọng mặc định có thể là `alloy`. |
| `piper` | Chạy model local | Cần cặp model/JSON và cấu hình `PIPER_MODEL_PATH`, `PIPER_CONFIG_PATH`. |
| `vieneu` | Chạy local hoặc remote | Cấu hình bằng `VIENEU_MODE`, `VIENEU_VOICE` và các biến VieNeu trong `.env`. |

Các giá trị mặc định chung được lưu trong [.env.example](../.env.example).
File này có thể được sao chép thành `.env` để đặt API key, model TTS và đường
dẫn model local.

## Ví dụ luồng thường dùng

### Chỉ dịch một file

Không nhất thiết dùng file chạy; có thể chạy trực tiếp:

```bash
python -m src.main translate input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --glossary glossary.csv
```

### Tạo audio từ thư mục đã dịch

```bash
python -m src.main tts --config configs/tts.json
```

Thư mục trong `vi_path` nên chỉ chứa các file chương tiếng Việt. Các file được
sắp xếp theo thứ tự số tự nhiên, ví dụ `1, 2, 10`.

### Dịch + tạo audio bằng một file

```bash
python -m src.main process --config configs/process.json
```

## Kiểm tra cấu hình

Xem tham số lệnh hiện có:

```bash
python -m src.main process --help
python -m src.main tts --help
```

Kiểm tra JSON hợp lệ bằng một công cụ chỉnh sửa/Terminal:

```bash
python -m json.tool configs/process.json
python -m json.tool configs/tts.json
```
