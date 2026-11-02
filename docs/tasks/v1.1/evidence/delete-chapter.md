# Xóa chương khỏi truyện

29/10/2026 · agent_verified theo yêu cầu bổ sung xóa chương.

UI có Xóa ở mỗi dòng và Xóa chương này trongchi tiết. Bước xác nhận ghi rõ tác động; Hủy/Escape trảfocus, không xóa. Khi thành công, dừng player nếu đang mở chương đó, bỏ ID khỏi lựa chọn/jobwizard và refresh danh sách/số liệu; xóa dòng cuối trang tự về trang hợp lệ. Phản hồi danh sách cũ không ghi đè kết quả mới.

API DELETE /api/v1/books/{book_id}/chapters/{chapter_id} với JSON revision. Kiểm tra sách/chương, revision và job pending/queued/running/stop_requested trong transaction BEGIN IMMEDIATE. Chặn khi job đang dùng chương (kểcả ghép); cho phép job biết rõ chỉ dùng chương khác và mẫu giọng độc lập. Job đã dừng có thể xóa chương nhưng không resume được snapshot mất nguồn. Preview cũ không confirm được nguồn đã xóa.

Xóa rowChapter/Artifact và vô hiệu truy cậpTXT/VI/audio theo ID; gỡ nullable Job.chapter_id, giữ snapshot/report và BookArtifact/bản ghép đã lưu. Không xóa vật lý file/cachedchunk, không đụng input/output nguồn. Trước xóa, lưu metadata Chapter/Artifact vào deleted-chapters/UUID.json; nếu transaction lỗi, rollback DB và dọn archive mới. Backup/restore gồm metadata này và file còn giữ. Chưa có UI khôi phục/xóa vĩnh viễn hoặc bulk delete; có thể nhập mới cùng số chương với ID mới. Không cần migrationDB.

4test mới PASS: scoping/revision/localheaders; queued/running/stop_requested conflict và job chương khác; xóa artifacts/404/giữ file/lịch sử/merged/FK/reimport; lỗi DB rollback archive, stale import/replay không resurrect; archive path symlink guard và backup/restore giữ metadata/file nhưng chương vẫn ở trạng thái đãxóa. Suite đầy đủ103testAPI PASS (49,177giây).

Browser PASS trên kho riêng: phát audio → mở xóa từ chi tiết → Escape/focus → xác nhận từ dòng → dừng player/bỏselection/artifact404 → reload; jobrunning trả409 → stop/đợistopped → xóa thànhcông; tổng0 cậpnhật; xóa dòng21 ởtrang2 tự về20dòngtrang1;390px khôngoverflow/lỗiJS/requestngoàilocal. Đã xem ảnh mobile-confirm.png; báo cáo browser-report.json/script verify-browser.cjs trongthưmục delete-chapter/. Build/diffcheck PASS.

Chạy lại: restartlauncher sau cậpnhậtAPI; mở truyện → danh sách chương → Xóa → Xác nhận xóa chương. Với job đang dùng chương, mở Công việc để dừng và đợi dừng xong. Test API: api/.venv/bin/python -m unittest discover -s tests -p test_chapter_deletion.py. Toàn suite: api/.venv/bin/python -m api.check. Browser script dùng Playwright/Edge qua NODE_PATH, chỉ cổng8100/8101, tạo data-dir timestamp và dừng process do script tạo.
