# Nhập văn bản trực tiếp

29/10/2026 · agent_verified theo yêu cầu không cần chọn file.

Trang truyện có ba cách nhập: File TXT / Nhập văn bản / Thư mục server. Form văn bản có số chương, tiêu đề tùy chọn và textarea, bộ đếm byteUTF-8; giới hạn256KiB/chương. Văn bản chỉ thành chương sau xem trước/xác nhận; khóa đổi cách nhập trong phiên preview. Hủy giữ nội dung trên form, reload mất bản nháp chưa lưu (UI ghi rõ). Không tự tách nhiều chương.

API POST /api/v1/books/{book_id}/text-imports nhận number/title/content và trả phiên import chuẩn. Dùng chung staging/hash, confirm/cancel, idempotence, phát hiện trùng và cập nhật có xác nhận. Không nhận path từ title; file staging tênUUID. Chương có tiêu đề cung cấp hoặc Chương N, provenance method=direct_text. Giữ nguyênbytesUTF-8/xuống dòng, nguồn cũ khi cập nhật; đầu vào dùng được với dịch/TTS/process. Không cần migrationDB.

Kiểm chứng:3test mới PASS (preview chưa tạo chương, exactUnicode/CRLF/emoji/download/provenance/replay/cross-book; cancel/duplicate/explicitupdate/oldsource; empty/NUL/Unicode/numbers/title/UTF8bytecap/localheaders). Bộ API đầy đủ99test PASS. Browser PASS tạo/dán/hủy/giữdraft/xác nhận/tải nguyênbytes/reload/cập nhật khôngtrùng/TTSgiảlập;390px khôngoverflow, khônglỗiJS/requestngoài local. Productionbuild vàdiffcheck PASS.

Báo cáo: direct-text/browser-report.json; ảnh mobile-input.png đã xem; source-checksums.json cùngthưmục. Script verify-browser.cjs dùngPlaywright/Edge, cổng8100/8101 vàkho giả lập timestamp, khôngdừng launcher8000 của người dùng.

Chạy lại: restartlauncher (`quit`/Ctrl+C rồi uv run --project api --frozen python -m api.dev), mở truyện → Nhập nội dung chương → Nhập văn bản → nhập số/tiêuđề/nội dung → Xem trước văn bản → Xác nhận. Trùng chương khác nội dung cần tick chọn và xác nhận cập nhật. Lần đầu nên thử chương ngắn.
