# Video ảnh minh họa theo truyện

Chế độ `--illustrate` tạo nhiều ảnh theo bản dịch, thêm zoom chậm và hòa ảnh (crossfade) trong video. Audio vẫn dùng file MP3 đã tạo bởi TTS; không gọi API tạo video của Gemini.

```text
Bản dịch + thời lượng audio từng chương
  → Chia thành các đoạn theo thứ tự truyện
  → Gemini viết prompt ảnh cho từng đoạn
  → Gemini tạo ảnh và lưu checkpoint
  → FFmpeg zoom nhẹ, hòa ảnh và ghép audio
  → MP4 + thumbnail + metadata như luồng hiện có
```

## 1. Chuẩn bị Gemini image bridge

Dùng mã nguồn tại `infra/gemini-web-to-api`. Thiết lập cookie/session trong `.env` **của infra**, theo [hướng dẫn của bridge](../infra/gemini-web-to-api/README.md). Không đưa cookie Google vào `.env` của novel2voice.

Chạy bridge bằng cách build từ thư mục infra để sử dụng đúng code local:

```bash
cd infra/gemini-web-to-api
cp -n .env.example .env
# Chỉnh cookie và account slot trong .env của infra trước khi chạy.
docker build -t novel2voice-gemini:local .
docker run --rm --name novel2voice-gemini \
  -p 127.0.0.1:4981:4981 --env-file .env \
  -v "$PWD/.cookies:/home/appuser/.cookies" novel2voice-gemini:local
```

Nếu container cùng tên đã chạy, dùng lại hoặc dừng nó trước khi chạy một bản khác. Thay vì Docker, có thể chạy `go run ./cmd/server` khi đã cài Go theo phiên bản trong `go.mod` của infra.

Từ một Terminal khác:

```bash
curl http://127.0.0.1:4981/health
curl http://127.0.0.1:4981/openai/v1/models
```

Health chỉ xác nhận server hoạt động. Model được chọn cần xuất hiện trong danh sách của tài khoản và có quyền tạo ảnh. Phiên bản hiện tại của bridge trả ảnh qua `/openai/v1/images/generations` với `response_format=b64_json`; novel2voice tải bytes này trực tiếp, không cố mở URL ảnh Google bằng client chưa đăng nhập.

## 2. Cấu hình novel2voice

Trong `.env` ở root project, thêm/chỉnh:

```ini
VIDEO_ILLUSTRATIONS=false
VIDEO_IMAGES_PER_CHAPTER=4
VIDEO_TRANSITION_SECONDS=1
VIDEO_ZOOM_AMOUNT=0.04
VIDEO_ILLUSTRATION_STYLE="Cinematic digital illustration, consistent character appearance, period-accurate settings, no text, captions, logos or watermarks."

GEMINI_IMAGE_BASE_URL=http://127.0.0.1:4981/openai/v1
GEMINI_IMAGE_MODEL=gemini-auto
GEMINI_IMAGE_API_KEY=not-needed
GEMINI_IMAGE_TIMEOUT_SECONDS=360
```

Giữ `VIDEO_ILLUSTRATIONS=false` để chỉ bật bằng cờ `--illustrate` khi cần. Đặt `true` nếu muốn mặc định bật cho pipeline CLI/bot. `--no-illustrate` tắt cho một lần chạy.

Client tạo ảnh có endpoint/model/key riêng. Bạn có thể giữ DeepSeek để dịch, VieNeu để đọc truyện và Gemini để tạo ảnh mà không thay cấu hình dịch hoặc TTS.

| Biến | Ý nghĩa |
|---|---|
| `VIDEO_IMAGES_PER_CHAPTER` | Từ 1–8 ảnh/chương; có thể ít hơn nếu nội dung quá ngắn. Mỗi video tối đa 48 ảnh |
| `VIDEO_TRANSITION_SECONDS` | Thời gian hòa ảnh, > 0 đến 5 giây; tự giảm và làm tròn theo FPS nếu cảnh ngắn |
| `VIDEO_ZOOM_AMOUNT` | Zoom tăng từ 1 đến `1 + giá trị`; `0.04` tương đương khoảng 4%; `0` tắt zoom, tối đa `0.2` |
| `VIDEO_ILLUSTRATION_STYLE` | Phong cách dùng chung, có thể ghi thêm ngoại hình nhân vật/bối cảnh để hướng dẫn model |
| `GEMINI_IMAGE_BASE_URL` | Base URL kết thúc ở `/openai/v1`, không kèm `/images/generations` |
| `GEMINI_IMAGE_MODEL` | Tên model có trong danh sách bridge, mặc định `gemini-auto` |
| `GEMINI_IMAGE_API_KEY` | Bridge local không bắt buộc key; dùng giá trị khác nếu proxy của bạn có xác thực |
| `GEMINI_IMAGE_TIMEOUT_SECONDS` | Timeout HTTP; nếu timeout, kiểm tra bridge trước khi thử lại vì upstream có thể đã tạo ảnh |

## 3. Render từ audio và bản dịch đã có

Đây là cách nên dùng để thử tính năng mà không dịch/TTS lại:

```bash
python -m src.main render-video output/chapter_1.mp3 \
  --translated-file output/chapter_1_vi.txt \
  --illustrate --title 'Tên truyện | Chương 1' \
  --output-dir output/illustrated_videos
```

Không cần chuẩn bị ảnh nền. Thumbnail lấy ảnh minh họa đầu tiên và ghép tiêu đề. Trong video, các ảnh phủ toàn khung hình, không lặp banner tiêu đề trên từng cảnh.

Có thể kết hợp metadata theo truyện:

```bash
python -m src.main render-video output/chapter_1.mp3 \
  --translated-file output/chapter_1_vi.txt \
  --story-config configs/story.json --metadata-provider deepseek \
  --illustrate --output-dir output/illustrated_videos
```

Tạo `configs/story.json` từ mẫu và chỉnh theo truyện trước khi chạy. Backend metadata tiếp tục lấy theo `--metadata-provider`/cấu hình dịch, còn prompt minh họa và tạo ảnh dùng Gemini image bridge.

Nhiều chương trong một video:

```bash
python -m src.main render-video output/chapter_1.mp3 output/chapter_2.mp3 \
  --translated-file output/chapter_1_vi.txt \
  --translated-file output/chapter_2_vi.txt \
  --chapters-per-video 2 --illustrate \
  --output-dir output/illustrated_videos
```

Truyền đúng một bản dịch tương ứng với mỗi audio, theo thứ tự đối số. Pipeline giữ cặp audio/bản dịch khi sắp xếp số chương tự nhiên. Ảnh được lập kế hoạch riêng theo từng chương, tránh lấy ảnh chương sau đặt vào chương trước.

## 4. Chạy toàn pipeline

```bash
python -m src.main process 'https://ixdzs8.com/read/644938/p1.html' \
  --max-chapters 1 \
  --translation-provider deepseek --provider vieneu \
  --glossary input/web/ixdzs8/644938/glossary.csv \
  --illustrate --video-output-dir output/illustrated_videos
```

Để thêm metadata và upload, truyền `--story-config configs/story.json --upload-youtube --youtube-privacy private` sau khi đã cấu hình OAuth/channel ID. Trong chế độ minh họa, `--story-config` và upload không yêu cầu ảnh nền thủ công.

`process` vẫn dịch lại khi chạy lại từ đầu. Nếu lỗi ở bước ảnh/render, dùng `render-video` với audio và bản dịch đã có để tiếp tục.

## 5. Bật cho Telegram

Thêm vào **profile truyện** trong `configs/telegram.json`:

```json
{
  "illustrate": true
}
```

Đây là trường bổ sung trong profile, không phải toàn bộ file bot config. Những trường đang có như URL, story config và background vẫn giữ theo schema profile hiện tại. `illustrate=false` tắt ảnh AI cho profile đó; bỏ trường này thì dùng `VIDEO_ILLUSTRATIONS` của máy.

Khởi động lại bot sau khi chỉnh. Job mới chụp giá trị `illustrate` trong profile; các job cũ có cấu hình đã lưu riêng. Bot hiển thị bước “Tạo ảnh minh họa” và tiến độ số ảnh. Một job vẫn xử lý một chương thành một video.

## 6. Cache, retry và đầu ra

Bên cạnh video sẽ có thư mục ảnh:

```text
output/illustrated_videos/
├── chapter_1.mp4
├── chapter_1.jpg
├── chapter_1.json
└── chapter_1.illustrations/
    └── <cache-key>/
        ├── manifest.json
        ├── illustrations.lock
        ├── chapter_1_scene_1.png
        ├── chapter_1_scene_2.png
        └── ...
```

Manifest giữ đoạn truyện, prompt đã lập và hash từng ảnh. Khi dùng story config còn có các sidecar metadata `.episode.json`/`.youtube.json` như trước.

- Mỗi ảnh thành công được ghi qua file tạm và checkpoint ngay. Lỗi ảnh sau không xóa ảnh trước.
- Chạy lại cùng lệnh sẽ dùng lại kế hoạch và các ảnh hợp lệ, chỉ tạo ảnh thiếu/hỏng/thay đổi hash.
- Đổi bản dịch, style, số ảnh/chương, model, endpoint, tên truyện hoặc hướng khung hình tạo cache khác.
- Đổi thời lượng audio giữ lại ảnh phù hợp nội dung và tính lại timeline; đổi transition/zoom chỉ làm render lại.
- `render-video --no-resume` tạo lại cả kế hoạch, ảnh và video, có thể tốn thêm lượt gọi.
- Không tự retry POST tạo ảnh khi gặp lỗi/timeout để tránh âm thầm tạo lại nhiều lần. Sau timeout vẫn có thể có ảnh đã được tạo phía Gemini nhưng chưa được nhận/lưu ở novel2voice.
- Nếu ảnh lỗi, pipeline dừng và giữ checkpoint. Không tự thay bằng ảnh không liên quan hoặc upload video minh họa chưa hoàn thành.
- File MP4 cũ được giữ nếu tạo ảnh hoặc render mới thất bại. Không có resume từng frame khi FFmpeg bị ngắt.

JSON render ghi danh sách `scenes`, nguồn ảnh, prompt, đoạn truyện, thời gian bắt đầu/thời lượng, mức zoom và thời gian chuyển cảnh thực tế.

## 7. Giới hạn của bản đầu

Đoạn minh họa được chia gần đều theo độ dài, ưu tiên ranh giới đoạn/câu; Gemini viết prompt dựa trên từng phần theo thứ tự. Đây chưa phải bộ phát hiện các tình tiết hoặc hồi truyện theo ngữ nghĩa.

Thời lượng ảnh được phân bổ **theo độ dài văn bản trong từng chương**, với tổng khớp thời lượng MP3 chương đó. Chưa dùng speech alignment nên thời điểm đổi hình có thể lệch so với câu đang đọc. Fade bắt đầu tại mốc đổi cảnh và kéo dài theo cấu hình, được làm tròn theo FPS.

Prompt yêu cầu lặp mô tả ngoại hình/phong cách nhất quán, nhưng chưa gửi ảnh tham chiếu nhân vật. Không bảo đảm nhân vật giữ nguyên mặt/trang phục qua mọi ảnh, đặc biệt giữa nhiều chương; nên xem lại trước upload. Có thể ghi đặc điểm cụ thể trong `VIDEO_ILLUSTRATION_STYLE`.

Ảnh được crop vừa khung hình, nên kích thước/aspect đầu ra Gemini không nhất thiết đúng số pixel được yêu cầu. Mặc định 4 ảnh/chương là số lượng khởi đầu; cân nhắc độ dài chương, thời gian tạo ảnh và tài nguyên máy khi tăng lên. Crossfade/zoom tốn công render hơn ảnh tĩnh, nhất là nhiều ảnh và 1080p.

Bản dịch dùng để tạo ảnh cần không rỗng và tối đa 60.000 ký tự/chương. Các đoạn quá ngắn so với một frame sẽ báo lỗi; giảm số ảnh/chương hoặc tăng FPS phù hợp. State/manifest có chứa nội dung truyện và prompt, cần được giữ riêng như các artifact khác.

## 8. Kiểm tra

```bash
python -m unittest discover -s tests -p test_illustrations.py -v
python -m unittest discover -s tests -v
```

Test dùng Gemini giả lập và FFmpeg thật. Có kiểm tra giữ nguyên thứ tự nội dung, cache khi lỗi một phần, không tự retry tạo ảnh, cặp audio/bản dịch sau sắp xếp và khung hình pha trộn thực tế khi crossfade. Không gọi tài khoản Gemini thật hoặc upload YouTube.

## 9. Thử từng bước riêng biệt

Script `scripts/test_illustrate_step.py` dùng chung service/cache của tính năng minh họa. Chạy từ root project, trong venv. Các lệnh dưới đây chỉ tạo file thử trong `output/illustrate_step_test`, không upload YouTube.

Chuẩn bị một cặp MP3/bản dịch của cùng chương; thay đường dẫn nếu dùng chương khác:

```bash
source .venv/bin/activate
test_audio=output/ixdzs8_644938_1_zh.mp3
test_text=output/ixdzs8_644938_1_zh_vi.txt
```

**Bước 1 — Chia đoạn, không gọi Gemini:**

```bash
python -m scripts.test_illustrate_step split --audio "$test_audio" --text "$test_text"
```

Terminal in nội dung từng đoạn và đường dẫn `manifest.json`. Kiểm tra thứ tự, mức độ chia hợp lý. Script mặc định chọn 2 ảnh để thử; có thể truyền `--images 4`, nhưng cần dùng cùng số ảnh qua mọi bước.

**Bước 2 — Viết prompt, chưa tạo ảnh:**

Bridge cần đang chạy với session/model hợp lệ. Kiểm tra server bằng `curl http://127.0.0.1:4981/health`, rồi chạy:

```bash
python -m scripts.test_illustrate_step prompts --audio "$test_audio" --text "$test_text"
```

Bước này gọi Gemini để tạo chữ nếu kế hoạch chưa có trong cache. Terminal in prompt tiếng Anh cho mỗi đoạn. Đọc lại bối cảnh, nhân vật và sự kiện trước khi chuyển sang tạo ảnh.

**Bước 3 — Tạo ảnh:**

```bash
python -m scripts.test_illustrate_step images --audio "$test_audio" --text "$test_text"
open output/illustrate_step_test
```

`open` là lệnh macOS. Mở thư mục `.illustrations/<cache-key>` và xem PNG. Nếu kế hoạch đã có, script chỉ tạo ảnh còn thiếu/hỏng. Nếu bỏ qua bước 2, bước 3 sẽ tự tạo prompt trước.

**Bước 4 — Render từ ảnh cache, không gọi Gemini:**

```bash
python -m scripts.test_illustrate_step render --audio "$test_audio" --text "$test_text"
open output/illustrate_step_test/ixdzs8_644938_1_zh.mp4
```

Bản thử dùng 1280×720, 15 fps và toàn bộ audio chương để giảm chi phí render so với 1080p/30 fps. Kiểm tra ảnh phủ khung, zoom nhẹ, hòa ảnh và audio liên tục. Nếu ảnh thiếu/hỏng hoặc đã bị sửa, bước này báo lỗi thay vì gọi Gemini; quay lại bước `images`.

Giữ nguyên `--audio`, `--text`, `--images`, `--title`, `--output-dir` và cấu hình model/style qua các bước để dùng cùng cache. Đổi chúng có thể tạo kế hoạch/cache khác. Tránh chỉnh tay manifest hoặc ảnh giữa bước `images` và `render`: hash được dùng để xác minh cache.

Chạy lại một bước sẽ tái sử dụng kết quả hợp lệ. Nếu muốn thử một bộ ảnh mới hoàn toàn, chọn `--output-dir output/illustrate_step_test_2` ở cả bốn lệnh; việc này có thể gọi Gemini lại.

### Khi bước prompts chờ lâu

Script in thông báo bắt đầu và cập nhật trạng thái mỗi 10 giây khi chưa xong. Đây là thông báo client vẫn đang chờ, không phải phần trăm tiến độ thật của Gemini. Bước lập prompt yêu cầu `reasoning_effort=low` và JSON để giảm suy luận không cần thiết.

Có thể chọn timeout ngắn hơn cho lần thử:

```bash
python -m scripts.test_illustrate_step prompts \
  --audio "$test_audio" --text "$test_text" --timeout 90
```

Timeout áp dụng cho thời gian chờ HTTP, không phải cam kết hủy tác vụ ở upstream. Nếu đã có một request chờ lâu, dùng Ctrl+C để dừng client và kiểm tra log bridge trước khi gửi lại. Không xóa cache: những prompt/ảnh đã lưu vẫn được giữ. Nếu request chat rất ngắn cũng không trả kết quả, kiểm tra session, model và kết nối upstream của bridge trước khi thử lại chương dài.
