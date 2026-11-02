# ADR 001 — Khung app/API local cho T01

Ngày: 28/10/2026. Trạng thái: **đã được thay thế bởi [ADR 002](002-vue-fastapi-sqlmodel.md)** theo lựa chọn của người dùng. Nội dung bên dưới giữ làm lịch sử quyết định, không phải hướng dẫn stack hiện tại.

## Quyết định

- `app/`: HTML/CSS và JavaScript ES modules, không dùng framework frontend hoặc dependency runtime bên ngoài ở bước này. Sidebar/bố cục theo mock đã review; dữ liệu chưa có thì hiện chưa kết nối, không điền số liệu mẫu.
- `api/`: FastAPI + Uvicorn, tiếp tục dùng Python với lõi hiện tại. API T01 chỉ cung cấp health; không import config/provider/model hoặc mở SQLite.
- `python -m api.dev`: launcher local chạy static app server và API process riêng. Mặc định app ở `127.0.0.1:8000`, API ở `127.0.0.1:8001`. Một lệnh khởi động cả hai; Ctrl+C/quit dừng cả hai.
- Frontend gọi API qua một module client, có timeout, validation response, loading/error/retry và tự kiểm tra khi quay lại tab. Không gọi provider hay truy cập file local trực tiếp.
- Bản local dùng CORS theo đúng hai origin localhost/127.0.0.1 và đúng cổng app. Chọn hai server để app vẫn mở khi API dừng, phục vụ flow nghiệm thu mất kết nối.
- `api stop`/`api start` là lệnh ở stdin launcher phục vụ kiểm tra local; không thêm endpoint web tắt/bật server. Không có worker trong T01.

## Lý do

Mục tiêu T01 là một shell/API thật có thể chạy và kiểm tra ngay, chưa cần database/worker/model. JavaScript module giúp không phải cài hoặc build Node để chạy tính năng này. FastAPI giữ được khả năng nối service Python và API schema khi thêm feature. Các thư mục tách riêng nên có thể thay cách build frontend sau này mà giữ hợp đồng API; thay stack sẽ cần quyết định riêng.

## Ranh giới và hệ quả

- Dependencies Python trực tiếp được pin tại `requirements-web.txt`; dependency chạy kiểm thử API ở `requirements-web-dev.txt`. Frontend không dùng CDN hoặc package runtime.
- API và app bind loopback, kiểm tra Host/Origin chính xác. Mutation API cần local Origin, header client và JSON; T01 chưa mở action ghi dữ liệu. Không dùng cookie/credential và không cho wildcard CORS.
- Static server chỉ phục vụ allowlist asset; không expose root repository hoặc `.env`.
- Đây là local launcher tối thiểu, không phải server Internet hay cơ chế process supervision hoàn chỉnh. Đóng gói/cài mới và kiểm chứng vận hành sâu thuộc T33.
- Startup readiness chỉ xác nhận HTTP của API. Doctor/provider, SQLite, queue, secret và nghiệp vụ vẫn ở các task sau.

## Tài liệu tham khảo

- [FastAPI middleware](https://fastapi.tiangolo.com/reference/middleware/)
- [Uvicorn settings](https://uvicorn.dev/settings/)
- [Yêu cầu v1.1](../v1.1-requirements.md)
- [Bản mock đã review](../ui/v1.1/README.md)
