# Hướng dẫn các lệnh chạy novel2voice

Tất cả lệnh dưới đây chạy từ thư mục gốc project, trong môi trường Python đã kích hoạt:

```bash
cd /home/himakevolution/Documents/Working/Project/novel2voice
source .venv/bin/activate
```

Xem toàn bộ tùy chọn của bản đang cài:

```bash
python -m src.main --help
python -m src.main tts --help
python -m src.main process --help
python -m src.main render-video --help
python -m src.main youtube-upload --help
```

## 1. Chuẩn bị môi trường

### Cài môi trường lần đầu

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Kiểm tra công cụ:

```bash
python --version
ffmpeg -version
ffprobe -version
python -m pip check
```

Kiểm tra provider TTS:

```bash
python -m src.main doctor
python -m src.main doctor --provider edge-tts
python -m src.main doctor --provider vieneu
python -m src.main doctor --provider piper
python -m src.main doctor --provider openai
python -m src.main voices
```

`doctor` không nạp model, gọi mạng hoặc xác nhận chất lượng giọng đọc.

## 2. Chỉ tạo audio từ tiếng Việt

Lệnh `tts` nhận TXT tiếng Việt đã dịch sẵn. Nó không dịch nội dung.

### Tạo audio cho một file

```bash
python -m src.main tts input/hai_dua_tre/hai_dua_tre.txt \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --rate '+0%' \
  -o output/hai_dua_tre.mp3
```

### Tạo audio cho nhiều file trong thư mục

```bash
python -m src.main tts input/truyen_vi \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural
```

Các file được sắp xếp theo thứ tự số tự nhiên: `1, 2, 10`.

### Ghép tất cả chương thành một MP3

```bash
python -m src.main tts input/truyen_vi \
  --provider edge-tts \
  --combine \
  -o output/toan_tap.mp3
```

`--combine` vẫn giữ MP3 riêng từng chương.

### Giữ chunk tạm để thuận tiện sửa/chạy lại

```bash
python -m src.main tts input/truyen_vi \
  --provider vieneu \
  --no-cleanup
```

### Tiếp tục từ checkpoint

```bash
python -m src.main tts input/truyen_vi \
  --provider vieneu \
  --resume \
  --state-dir output/.state
```

### Tạo lại audio, bỏ qua kết quả cache

```bash
python -m src.main tts input/truyen_vi \
  --provider vieneu \
  --no-resume
```

### Retry và xử lý lỗi

```bash
# Chỉ thử lại tối đa 2 lần cho mỗi đoạn/chương khi gặp lỗi
python -m src.main tts input/truyen_vi \
  --provider vieneu \
  --retries 2

# Dừng batch ngay khi gặp chương lỗi
python -m src.main tts input/truyen_vi \
  --provider vieneu \
  --retries 0 \
  --fail-fast
```

Theo dõi checkpoint:

```bash
python -m src.main status
python -m src.main status --state-dir output/.state
```

## 3. Chỉ dịch truyện

### Dịch một file

```bash
python -m src.main translate input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --glossary input/my_story/glossary.csv \
  -o output/chapter_1_vi.txt
```

### Dịch bằng OpenAI hoặc endpoint tương thích

```bash
python -m src.main translate input/my_story/chapter_1.txt \
  --translation-provider openai \
  --model gpt-4o-mini \
  --glossary input/my_story/glossary.csv
```

### Dịch cả thư mục

```bash
python -m src.main translate input/my_story \
  --translation-provider deepseek \
  --glossary input/my_story/glossary.csv
```

`translate` chỉ tạo bản dịch; không tạo MP3.

## 4. Dịch + tạo audio

Lệnh `process` luôn thực hiện bước dịch, kể cả khi đầu vào là thư mục hoặc URL.

### File hoặc thư mục TXT

```bash
python -m src.main process input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --model deepseek-chat \
  --provider vieneu \
  --voice 'Ngọc Lan' \
  --glossary input/my_story/glossary.csv
```

```bash
python -m src.main process input/my_story \
  --translation-provider openai \
  --model gpt-4o-mini \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural
```

Với URL ixdzs8:

```bash
python -m src.main fetch 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 2

python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 2 \
  --translation-provider deepseek \
  --model deepseek-chat \
  --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv
```

## 5. Chỉ tạo video từ audio có sẵn

Tất cả MP3 phải thuộc cùng một bộ truyện.

### Xem kế hoạch chia tập

```bash
python -m src.main plan-videos \
  output/chapter_1.mp3 \
  output/chapter_2.mp3 \
  output/chapter_3.mp3 \
  --chapters-per-video 2
```

### Render video không metadata truyện

```bash
python -m src.main render-video \
  output/chapter_1.mp3 \
  output/chapter_2.mp3 \
  --background assets/background.jpg \
  --title 'Tên truyện | Chương 1–2' \
  --chapters-per-video 2 \
  --output-dir output/videos
```

### Render một chương và tạo metadata bằng story config

```bash
python -m src.main render-video \
  output/chapter_1.mp3 \
  --translated-file output/chapter_1_vi.txt \
  --story-config configs/story.json \
  --metadata-provider deepseek \
  --metadata-model deepseek-chat \
  --background assets/background.jpg \
  --output-dir output/videos
```

Mặc định mặc không truyền metadata. Story config cần `--translated-file` tương ứng với audio và dùng chung một truyện.

## 6. Tạo audio và video trong cùng một lệnh

### Từ TXT tiếng Việt

```bash
python -m src.main tts input/truyen_vi \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --background assets/background.jpg \
  --story-config configs/story.json \
  --video-title 'Tên truyện' \
  --chapters-per-video 1 \
  --video-output-dir output/videos
```

### Từ một file tiếng Việt

```bash
python -m src.main tts input/hai_dua_tre/hai_dua_tre.txt \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --background assets/background.jpg \
  --video-title 'Hai đứa trẻ'
```

### Từ TXT gốc: dịch + tạo audio + video

```bash
python -m src.main process input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --provider vieneu \
  --glossary input/my_story/glossary.csv \
  --background assets/background.jpg \
  --story-config configs/story.json \
  --video-title 'Tên truyện' \
  --chapters-per-video 1 \
  --video-output-dir output/videos
```

Không truyền `--background` thì lệnh `tts` hoặc `process` chỉ dừng ở MP3.

## 7. Tạo audio, video và upload YouTube

### Kết nối kênh YouTube một lần

Chuẩn bị file OAuth Desktop app tại `.secrets/youtube/client_secret.json`, sau đó:

```bash
python -m pip install -r requirements-youtube.txt
python -m src.main youtube-auth
```

Thêm channel ID được lệnh in ra vào `.env`:

```ini
YOUTUBE_CHANNEL_ID=TEN_CHANNEL_ID
YOUTUBE_PRIVACY=private
```

### Upload trong cùng pipeline

```bash
python -m src.main tts input/truyen_vi \
  --provider edge-tts \
  --voice vi-VN-HoaiMyNeural \
  --background assets/background.jpg \
  --story-config configs/story.json \
  --chapters-per-video 1 \
  --upload-youtube \
  --youtube-privacy private
```

```bash
python -m src.main process input/my_story/chapter_1.txt \
  --translation-provider deepseek \
  --provider vieneu \
  --background assets/background.jpg \
  --story-config configs/story.json \
  --upload-youtube \
  --youtube-privacy private
```

Chỉ render local thì bỏ `--upload-youtube`.

### Xem trước hoặc upload MP4 đã render

```bash
python -m src.main youtube-upload output/videos/chapter_1.mp4 --dry-run

python -m src.main youtube-upload output/videos/chapter_1.mp4 \
  --privacy private

python -m src.main youtube-status
```

Upload kèm metadata tùy chỉnh:

```bash
python -m src.main youtube-upload output/videos/chapter_1.mp4 \
  --metadata-file configs/youtube.json \
  --privacy private
```

Upload kèm tiêu đề/mô tả/tag trực tiếp:

```bash
python -m src.main youtube-upload output/videos/chapter_1.mp4 \
  --title 'Tên truyện | Chương 1' \
  --description 'Mô tả chương 1' \
  --tag 'truyện audio' \
  --tag 'audiobook' \
  --privacy private
```

## 8. Chạy bằng file cấu hình JSON

### Cấu hình tts

Tạo file riêng:

```bash
cp -n configs/tts.example.json configs/tts.json
```

Chỉnh `configs/tts.json`, sau đó chạy:

```bash
python -m src.main tts --config configs/tts.json
```

Ví dụ các khóa quan trọng:

```json
{
  "command": "tts",
  "vi_path": "input/truyen_vi",
  "provider": "edge-tts",
  "voice": "vi-VN-HoaiMyNeural",
  "rate": "+0%",
  "cleanup_temp": true,
  "combine": false,
  "concurrency": 3,
  "resume": true,
  "state_dir": "output/.state",
  "retries": 2,
  "continue_on_error": true,
  "background": "assets/background.jpg",
  "story_config": "configs/story.json",
  "video_title": "Tên truyện",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false,
  "youtube_metadata_file": null,
  "youtube_privacy": "private",
  "dry_run": false
}
```

Tùy chọn CLI ghi đè giá trị trong JSON:

```bash
python -m src.main tts --config configs/tts.json \
  --provider edge-tts \
  --voice vi-VN-NamMinhNeural \
  --chapters-per-video 2
```

### Cấu hình chỉ tạo audio

```json
{
  "command": "tts",
  "vi_path": "input/truyen_vi",
  "provider": "vieneu",
  "voice": "Ngọc Lan",
  "combine": true,
  "output_audio": "output/toan_tap.mp3",
  "background": null,
  "upload_youtube": false,
  "dry_run": false
}
```

### Cấu hình audio + video

```json
{
  "command": "tts",
  "vi_path": "input/truyen_vi",
  "provider": "edge-tts",
  "voice": "vi-VN-HoaiMyNeural",
  "combine": false,
  "background": "assets/background.jpg",
  "story_config": "configs/story.json",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false,
  "dry_run": false
}
```

### Cấu hình audio + video + YouTube

```json
{
  "command": "tts",
  "vi_path": "input/truyen_vi",
  "provider": "edge-tts",
  "voice": "vi-VN-HoaiMyNeural",
  "background": "assets/background.jpg",
  "story_config": "configs/story.json",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": true,
  "youtube_metadata_file": null,
  "youtube_privacy": "private",
  "dry_run": false
}
```

### Cấu hình process

```bash
cp -n configs/process.example.json configs/process.json
python -m src.main process --config configs/process.json
```

Ví dụ:

```json
{
  "command": "process",
  "input_path": "input/my_story/chapter_1.txt",
  "translation_provider": "deepseek",
  "model": "deepseek-chat",
  "provider": "vieneu",
  "voice": "Ngọc Lan",
  "glossary_path": "input/my_story/glossary.csv",
  "cleanup_temp": true,
  "concurrency": 3,
  "max_chapters": 1,
  "output_audio": null,
  "background": "assets/background.jpg",
  "story_config": "configs/story.json",
  "video_title": "Tên truyện",
  "video_output_dir": "output/videos",
  "chapters_per_video": 1,
  "upload_youtube": false,
  "youtube_privacy": "private"
}
```

## 9. Dry run

Dry run của `tts` kiểm tra TXT, ảnh nền, story config, kế hoạch video và tùy chọn upload mà không chạy TTS, FFmpeg, OAuth hoặc ghi output/state.

```bash
python -m src.main tts --config configs/tts.json --dry-run
```

Hoặc bật trong JSON:

```json
{
  "command": "tts",
  "vi_path": "input/truyen_vi",
  "background": "assets/background.jpg",
  "dry_run": true
}
```

Dry run upload YouTube độc lập:

```bash
python -m src.main youtube-upload output/videos/chapter_1.mp4 --dry-run
```

## 10. Điều khiển bằng Telegram

Tạo profile:

```bash
cp -n configs/telegram.example.json configs/telegram.json
python -m src.main telegram-bot --profiles configs/telegram.json
```

Trên macOS có thể giữ Terminal thức:

```bash
caffeinate -i python -m src.main telegram-bot --profiles configs/telegram.json
```

Các lệnh Telegram phổ biến:

```text
/menu
/run wallstreet 1
/status
/status 12
/schedule wallstreet 2 2026-12-20 18:30
/schedule-day wallstreet 10 2026-12-20 3
/retry 12
/retry 12 2026-12-20 18:30
/now 12
/cancel 12 13
/clear finished
/clear failed
```

Thời gian theo `Asia/Ho_Chi_Minh`.

## 11. Tạo file chương trống

```bash
python generate_files.py input/truyen_vi 1
python generate_files.py input/truyen_vi 21
```

Lệnh tạo tối đa 20 file theo dạng `1_vi.txt`, `2_vi.txt`, ... và không ghi đè file đã tồn tại.

## 12. Kiểm tra JSON và dự án

```bash
python -m json.tool configs/tts.json
python -m json.tool configs/process.json
python -m json.tool configs/story.json
python -m unittest discover -s tests -v
```

## 13. Bảng lệnh nhanh

| Mục tiêu | Lệnh chính |
|---|---|
| Chỉ lấy chương web | `fetch` |
| Chỉ dịch | `translate` |
| Chỉ tạo audio | `tts` |
| Dịch + tạo audio | `process` |
| Dịch + audio + video | `process` kèm `--background` |
| Audio + video | `tts` kèm `--background` |
| Xem cách chia video | `plan-videos` |
| Render video có sẵn | `render-video` |
| Xem trước upload YouTube | `youtube-upload --dry-run` |
| Upload YouTube | `youtube-upload` |
| Kiểm tra upload | `youtube-status` |
| Kiểm tra môi trường TTS | `doctor` |
| Xem checkpoint TTS | `status` |
| Liệt kê giọng Edge | `voices` |
| Chạy Telegram | `telegram-bot` |

## 14. Quy tắc quan trọng

- Chạy mọi lệnh trong thư mục gốc project.
- `tts` chỉ nhận TXT tiếng Việt đã có; `process` luôn dịch đầu vào.
- `--provider` chọn TTS; `--translation-provider` chọn dịch thuật.
- `--background` kích hoạt render video trong `tts` và `process`.
- `--story-config` cần `--background` và không dùng cùng `--youtube-metadata-file`.
- `--upload-youtube` cần đã chạy `youtube-auth`, có channel ID và token OAuth.
- `tts --combine` chỉ gộp thư mục thành một file, không thay thế MP3 riêng từng chương.
- `process` chưa hỗ trợ dry run riêng; dùng `tts --dry-run` để kiểm tra luồng tiếng Việt.
- Chỉ truyền MP3 của cùng một truyện vào `plan-videos` hoặc `render-video`.
- Không chạy bot và CLI cùng ghi một job hoặc thư mục đầu ra.
- Giữ `.env`, glossary, OAuth token, session DeepSeek và thư mục `output/.state` riêng tư.
