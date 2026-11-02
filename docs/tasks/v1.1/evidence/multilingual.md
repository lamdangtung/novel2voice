# Bổ sung đa ngôn ngữ nguồn

29/10/2026 · agent_verified, theo yêu cầu mở rộng ngoài EN/VI.

Tạo/sửa truyện có22ngôn ngữ: Việt, Anh, Trung, Nhật, Hàn, Pháp, Đức, Tây Ban Nha, Bồ Đào Nha, Ý, Nga, Thái, Indonesia, Malaysia, Hindi, Ả Rập, Thổ Nhĩ Kỳ, Ukraina, Ba Lan, Hà Lan, Thụy Điển, Phần Lan. API/catalog/database dùng chung src/languages.py; danh sách hiển thị đúng nhãn, không coi mọi mã ngoài vi là tiếng Anh.

Dịch/process lấy ngôn ngữ gốc vào snapshot, prompt/hash và provenance, đầu raVI. Retry giữ đúng ngôn ngữ và tái dùng VI khi lỗiTTS. TTS trực tiếp vẫn yêu cầuVI. Đổi ngôn ngữ giữ file, đánh dấu bản dịch/audio cũ cần kiểm tra và tăng chapter revision; snapshot cũ bị chặn. Glossary CSV giữ header en,vi tương thích dữ liệu cũ, thuật ngữ nguồn có thể chứa chữ bất kỳ.

Schema3 nâng cấp tự động từ1/2 dưới schema.lock: SQLitebackup trước, rebuild CHECKconstraint trong transaction, giữ ID/metadata/con và unique index, foreign_key_check trướccommit, rollback khi lỗi. Không cần nhập lại truyện. Restart launcher để API/migration mới được áp dụng.

Kiểm chứng:
-96test API PASS (`api/.venv/bin/python -m api.check`), gồm catalog/toàn bộ22mã/create/edit/reload/invalidcodes; nâng cấp DBschema2 có chương/artifact, backup/unique/FK/idempotence; Chinese process/retry và đổi ngôn ngữ chặn snapshot cũ. Test health được tách sang data_dir tạm để không đọc heartbeat worker đang chạy của người dùng.
- Prompt builder thật trong rootSDK khớp contract API cho22ngôn ngữ, không gọi API.
- Browser PASS: tạo truyện Trung, nhãn đúng, đổi Nhật/reload, đổi vềTrung, nhậpTXTTrung và chạyprocess giả lập thành công, snapshot source_language=zh;390px khôngoverflow, khônglỗiJS/requestngoài local. Xem multilingual/browser-report.json và ảnh cùng thư mục.
- Production build và git diff --check PASS.

Giới hạn: hỗ trợ khai báo ngôn ngữ và chuyển source→VI không đồng nghĩa đã nghiệm thu chất lượng dịch vụ thật cho22ngôn ngữ. VieNeu vẫn dùng đầu vàoVI. Không tự gọi dịch vụ tính phí. Chế độ fake kiểm tra luồng/hash/snapshot, không đánh giá bản dịchAI.

Chạy lại UI: restart `uv run --project api --frozen python -m api.dev`, vào Thư viện chọn ngôn ngữgốc. Dùng --verification vàdata-dir riêng để chạy process khôngchi phí. Browser script multilingual/verify-browser.cjs dùng8100/8101 với kho timestamp và dừng cácprocess do nó tạo.
