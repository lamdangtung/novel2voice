# Tài liệu novel2voice trên Notion

Ngày chuyển: 28/10/2026. Đây là bản sao thủ công, chưa có đồng bộ tự động.

Trang gốc: [novel2voice](https://app.notion.com/p/40761b540cf680579b4dec6df11c61fb).

- [Tổng quan dự án](https://app.notion.com/p/40761b540cf681e28f3fde2a092531eb?pvs=204)
- [Roadmap v1.0 → v2.0](https://app.notion.com/p/40761b540cf681f69840d68c1e5c39c7?pvs=204)
- [v1.1 — Web app](https://app.notion.com/p/40761b540cf6818f8841eddc3522be39?pvs=204)
- [Requirements v1.1](https://app.notion.com/p/40761b540cf68138a918e0a678f59f15?pvs=204)
- [UI/UX — Mock đã review](https://app.notion.com/p/40761b540cf681fab7e8d206f8b14326?pvs=204)
- [34 task và flow nghiệm thu](https://app.notion.com/p/40761b540cf6815ba247cae5fcde0c78?pvs=204)

Đã chuyển roadmap, requirements, toàn bộ T01–T34, tài liệu UI/UX, bản mock HTML và 8 ảnh tham chiếu. Đã tạo 34 issue trong milestone v1.1 trên Linear; xem [bảng ánh xạ](linear-reference.md). v1.1 đang triển khai: T01/T02 đã được người dùng chấp nhận; T03 đã kiểm tra, chờ người dùng nghiệm thu.

## Cập nhật về sau

- Dùng page ID trong [manifest](notion-manifest.json) để cập nhật trang hiện có, tránh tạo trùng.
- Đối chiếu thay đổi trên cả Notion và repository trước khi ghi; không thay toàn trang nếu người dùng đã sửa nội dung.
- Khi cập nhật, ghi ngày và nguồn, chuyển các link nội bộ sang trang Notion tương ứng. Giữ child page và media có sẵn.
- Manifest ghi checksum nguồn tại lần chuyển này; checksum không tự cập nhật và không chứng minh Notion vẫn giống repository sau khi có chỉnh sửa.
- File HTML đính kèm là mock tương tác; audio/tác vụ mô phỏng. Icon có thể cần Internet.
- Các file mã nguồn/ảnh vẫn được giữ trong project; không upload .env, API key hoặc dữ liệu nhạy cảm.

## Bàn giao triển khai

- [T02 — Workspace kiểm thử và flow nghiệm thu](https://app.notion.com/p/40761b540cf681afa0c6d8a711ec9b7d?pvs=204): đã được người dùng chấp nhận.
- [T03 — Kiểm tra môi trường trên web](https://app.notion.com/p/40761b540cf681e09f01f45818d6eba1?pvs=204): 57 test đạt; chờ người dùng verify.

Cập nhật29/10/2026: T04–T33 agent_verified, T34 còn mở. [Hướng dẫn web app](https://app.notion.com/p/40861b540cf68112817bc4d9c858119c?pvs=204) · [Nghiệm thu/vận hành](https://app.notion.com/p/40861b540cf681d5af77d94983c443a6?pvs=204).
