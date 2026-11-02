# ADR 002 — Vue, FastAPI, SQLModel và uv/pnpm

Ngày: 28/10/2026. Trạng thái: **theo lựa chọn của người dùng, đã áp dụng vào T01**. Thay thế quyết định frontend buildless ở [ADR 001](001-local-web-stack.md).

## Stack đã chốt

| Tầng | Công nghệ | Cách áp dụng |
|---|---|---|
| Frontend | Vue 3, Vite, Tailwind CSS | Single-File Component dùng Composition API / `<script setup>`; layout bằng utility class, token chung trong `style.css` |
| Backend | FastAPI, Python 3.12, Uvicorn | Type hints và Pydantic response model; OpenAPI `/openapi.json`, Swagger UI `/docs` |
| Database/ORM | SQLite + SQLModel | Dependency được pin và smoke test trong bộ nhớ ở T01; bảng, session/repository và migration nghiệp vụ triển khai ở T04 |
| Python tooling | uv | `api/pyproject.toml`, `api/uv.lock`, môi trường riêng `api/.venv` |
| Node tooling | pnpm | `app/package.json`, `app/pnpm-lock.yaml`, phiên bản packageManager được pin |

Không coi tốc độ cài đặt của package manager là tiêu chí nghiệm thu tính năng. Mục tiêu là cấu hình có lockfile, cài/chạy lại được, và giữ cùng flow đã thống nhất.

## Cấu trúc

```text
app/
  src/
    App.vue
    components/ApiConnection.vue
    composables/useApiHealth.js
    lib/api-client.js
    style.css
  vite.config.js
  package.json
  pnpm-lock.yaml
api/
  main.py
  settings.py
  dev.py
  pyproject.toml
  uv.lock
src/                      # Lõi CLI/TTS v1.0 hiện có
```

Component nhận trạng thái từ composable; API client là nơi gọi HTTP. Không đưa provider, SQLModel hoặc filesystem vào frontend. Chỉ dùng CSS global cho Tailwind import, token và base; giao diện chính viết bằng utility class trong SFC.

## Khởi động và cách ly môi trường

Chạy từ root repository:

```bash
pnpm --dir app install --frozen-lockfile
uv sync --project api --frozen
uv run --project api --frozen python -m api.dev
```

App mặc định `http://127.0.0.1:8000`, Swagger `http://127.0.0.1:8001/docs`. Đổi cổng bằng `--app-port` và `--api-port` khi chạy launcher.

`uv --project api` dùng môi trường API riêng; không đồng bộ/xóa package trong `.venv` TTS đã có ở root. Migration dependency của CLI/model toàn bộ không nằm trong T01. `requirements.txt` CLI được giữ cho đến khi xử lý tương thích ở T33.

Launcher quản lý Vite và Uvicorn thành hai process group, không để Vite giành stdin. `api stop`/`api start` chỉ tắt/bật backend, giao diện tiếp tục phục vụ; `quit`/Ctrl+C dừng toàn bộ process con.

## API docs và ranh giới local

- Swagger assets lấy từ package `swagger-ui-dist` đã pin, phục vụ qua API, không dùng CDN khi mở docs.
- Header client cho Swagger Try it out được thêm bằng request interceptor. Chỉ chấp nhận origin chính xác của app hoặc API local theo cổng đang dùng. CORS chỉ cấp cho origin app, không wildcard.
- Vite bind loopback và có middleware kiểm tra Host/Origin trước middleware mặc định; filesystem giới hạn trong app, chặn `.env`, private key và `.git`. Không mở root repository.
- HMR dùng WebSocket local; development CSP cho phép style inline phục vụ HMR. Đây là cấu hình dev, chưa phải bản đóng gói production ở T33.
- Không chạy script telemetry `@scarf/scarf` khi cài pnpm; chỉ cho build script của tool cần thiết trong `pnpm-workspace.yaml`.

## Phạm vi giữ nguyên

T01 vẫn là health/UI shell, chưa mở dữ liệu truyện hoặc khởi động worker/model. SQLModel được chốt cho dữ liệu mới ở T04; checkpoint SQLite v1.0 hiện có phải được migration/ánh xạ an toàn, không tự viết lại ở lần đổi stack này. Mock đã duyệt giữ nguyên làm tham chiếu thiết kế.

## Nguồn chính thức

- [Vue Quick Start](https://vuejs.org/guide/quick-start.html)
- [Tailwind + Vite](https://tailwindcss.com/docs/installation/using-vite)
- [FastAPI self-hosted Swagger UI](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/)
- [SQLModel và SQLite](https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/)
- [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/)
