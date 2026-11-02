# App — Vue/Vite/Tailwind

Vue 3 Composition API, Single-File Components dùng `<script setup>`. Tailwind CSS qua plugin Vite, token trong `src/style.css`, API client trong `src/lib/`, composable trong `src/composables/`.

Cần Node 22.12+ (đã kiểm tra Node 24) và pnpm theo phiên bản packageManager trong package.json. Chạy từ root project:

```bash
pnpm --dir app install --frozen-lockfile
uv sync --project api --frozen
uv run --project api --frozen python -m api.dev
```

Mở http://127.0.0.1:8000. Launcher tự cấu hình API origin và cổng Vite. `api stop` / `api start` ở terminal launcher dùng để verify retry. `quit` hoặc Ctrl+C dừng app/API/worker do launcher tạo.

Build frontend:

```bash
pnpm --dir app build
```

Không mở index.html trực tiếp. Đã có đầy đủ các flow thư viện/import/cấu hình/dịch/TTS/process/ghép/mẫu giọng/dashboard. Xem [hướng dẫn](../docs/v1.1-user-guide.md). Xem [ADR 002](../docs/decisions/002-vue-fastapi-sqlmodel.md) và [flow nghiệm thu](../docs/tasks/v1.1/evidence/T01.md).

## Kiểm thử T02

Thêm `--verification` vào launcher để bật menu **Kiểm thử offline** và banner cố định. `VerificationWorkspace.vue` dùng API thật trong vùng kiểm thử, có tạo/reset, lỗi/delay, audio thử và báo cáo; không phải mock HTML đã lưu trước đây. Khi không bật flag, các chức năng này không hiện trong app.

## T03 — Môi trường

`#environment` gọi doctor thật qua API; xem kết quả, thiếu thành phần và cách xử lý. Khi bật `--verification`, có fixture thiếu dependency/model và nhãn giả lập. Xem [T03 evidence](../docs/tasks/v1.1/evidence/T03.md).
