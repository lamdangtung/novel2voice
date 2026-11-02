# API — FastAPI/uv/SQLModel

API phục vụ thư viện/import/cấu hình/audio/job/dashboard; worker riêng gọi lõi CLI qua bridge SDK. Không nạp model trong process API. Doctor/cấu hình đọc môi trường server nhưng không trả key.

## Cài và chạy từ root repository

```bash
pnpm --dir app install --frozen-lockfile
uv sync --project api --frozen
uv run --project api --frozen python -m api.dev
```

App: http://127.0.0.1:8000. Swagger: http://127.0.0.1:8001/docs. `api stop`, `api start`, `quit` hoặc Ctrl+C trong terminal launcher. Có thể đổi cặp cổng bằng `--app-port 8100 --api-port 8101`.

uv quản lý `api/.venv` và `api/uv.lock`, không sửa `.venv` TTS tại root. `sqlmodel` đã pin, schema/session/migration nghiệp vụ đã triển khai. Checkpoint SQLite v1.0 được giữ nguyên.

Chạy API riêng:

```bash
uv run --project api --frozen python -m api.main --port 8001 --app-port 8000
```

Không chạy thêm cùng cổng khi launcher đang chạy. Swagger JS/CSS được self-host từ `app/node_modules/swagger-ui-dist`; cài pnpm trước để UI docs dùng được offline.

## Contract

`GET /api/v1/health`: HTTP 200, Cache-Control no-store. Response model có type hints và tự xuất vào `/openapi.json`:

```json
{
  "status": "ok",
  "service": "novel2voice-api",
  "version": "1.0.0",
  "scope": "T27",
  "verification_mode": false,
  "components": { "database": "not_implemented", "worker": "not_implemented" }
}
```

Lỗi: `{"error":{"code":"NOT_FOUND","message":"..."}}`. Health không xác nhận khả năng TTS hoặc chất lượng giọng đọc. Version vẫn 1.0.0 tới khi phát hành v1.1.

API bind loopback; Host/Origin phải đúng localhost/127.0.0.1 và cổng cấu hình. CORS chỉ cho app origin. Mutation cần Origin app hoặc API local (Swagger), `X-Novel2Voice-Client: web`, JSON, rồi validation riêng của feature. Header client không thay thế xác thực nếu mở LAN/Internet. Không có mutation nghiệp vụ trong T01.

Kiểm tra riêng API:

```bash
uv run --project api --frozen python -m unittest discover -s tests -p 'test_web_shell.py' -v
```

## T02 — Kiểm thử offline (opt-in)

```bash
uv run --project api --frozen python -m api.dev --verification
```

API lúc này mới mount `/api/v1/verification/workspaces` (list/create/reset/self-check và report/audio kiểm thử). Chế độ thường trả 404 và không đưa các route này vào OpenAPI. Header bảo vệ mutation vẫn bắt buộc.

Dữ liệu ở `.verification/workspaces/<tên>`, không nhận đường dẫn tùy ý. Provider giả lập, âm tone và bản dịch mẫu được ghi nhãn, không nối registry sản xuất. Flow chi tiết: [T02 evidence](../docs/tasks/v1.1/evidence/T02.md).

## T03 — Doctor môi trường

`POST /api/v1/environment/doctor` với `{"provider":"vieneu","scenario":"real"}` trả `DoctorReport` trong OpenAPI. Provider: vieneu/piper/edge-tts/openai. Route có cùng bảo vệ Origin/header/JSON như các mutation local.

Dùng `src.doctor.check_environment`, chạy probe có timeout bằng `.venv/bin/python` gốc để tìm dependency, không import SDK/nạp model. API thêm python-dotenv để đọc lại `.env`; biến môi trường server được ưu tiên. Không trả key, endpoint hay nội dung file cấu hình. Không sửa .env/model.

Chỉ khi `--verification`: cho phép scenario `missing_dependency` hoặc `missing_model` (Piper/VieNeu), lấy từ `tests/fixtures/t03/scenarios.json`; kết quả ghi rõ giả lập. Flow: [T03 evidence](../docs/tasks/v1.1/evidence/T03.md).

## Vận hành hiện tại

Xem [hướng dẫn sử dụng](../docs/v1.1-user-guide.md). `python -m api.check` chạy regression API offline; SDK tests chạy bằng root .venv. `python -m api.backup --help` có backup/restore vào đích mới. Launcher/API/worker hỗ trợ --data-dir cho kho riêng.

## Ngôn ngữ nguồn

GET /api/v1/books/workspace/languages trả catalog22ngôn ngữ. BookInput và schema3 kiểm tra cùng catalog src/languages.py. Dịch/process giữ source_language trongsnapshot/provenance vàprompt hash. Nâng cấp schema1/2 sao lưu trước, rollback transaction khi lỗi.
