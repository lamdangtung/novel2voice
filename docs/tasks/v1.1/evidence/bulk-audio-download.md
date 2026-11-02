# Tải audio hàng loạt theo lựa chọn hoặc khoảng chương

29/10/2026 · agent_verified.

UI AudioBulkDownload trong trang truyện: Chương đang chọn (kểcả ở nhiều trang) hoặc Khoảng chương x–y bao gồmhaiđầu, độc lập filter/checkbox. Kiểm tra trước tải, hiển thị số/dung lượngMP3 hợp lệ, danh sách/lý do bỏqua chương không tồn tại/thiếu audio/cũ/file hỏng. Chỉ tải audio hiện hành đang chọn, đúng nguồn/cấu hình/bản dịch/hash. Nếu khôngfilehợp lệ, khôngcho tạoZIP. Tối đa500chương/2GiB mỗi phiên.

API POST /books/{book}/audio-downloads/preview → /{id}/prepare → GET /{id}/file. Scope UUID vàbook được kiểmtra, selectedIDs khôngđược lẫn truyện hoặc đãxóa, mode/khoảng/duplicate/giớihạn đượcràngbuộc. Snapshot lưu chapter revision/source hash/audio ID/hash, kiểm tra trước vàsau copy; nguồn/audio đổi chặn chuẩn bịZIP. ZIPchứa riêngMP3 ZIP_STORED, tên số đệm tự nhiên +tiêuđề đãloại dấu path/ký tựđiềukhiển, UTF8. Không chạyTTS/ghép, không sửa nguồn.

ZIPtạo ởaudio-downloads/UUID trongkho bằng chunk1MiB, kiểmhash khi copy, .partial chỉrename sauhoàn tất, lỗi dọnpartial. Kiểm dunglượngđĩa trước tạo. Frontendchỉ nhậnJSON rồi kích hoạt nativebrowserdownload, không tải ZIPthànhBlob. FileResponse hỗ trợRange; sharedlock giữ tới khi streamxong/khi disconnect, cleanup khôngxóa fileđang tải. Chuẩn bị dùng exclusive lock, retry cùngphiên dùng lạiZIP. TTL30phút, tốiđa20phiên; expiredcache được dọn khi tạo previewtiếp theo. ZIPtạm không thuộcbackup. Không cần migrationDB.

Kiểm chứng:5testAPI mới PASS (range/gaps/missing/order/exactbytes/reprepare/Range; selectedacrosspages/unsafe names/validation/cross-book/localheaders; stale/corrupt/unselected/empty; source/selection/deletion snapshot guard; tổngbytes/diskfailure/partialcleanup/TTL/sharedlock). Toàn bộ108testAPI PASS (61,882giây). Productionbuild/diffcheck PASS.

Browser PASS:45chương, audio ở1/2/10/21/45; chọn1/21/45 trên3trang → nativeZIP đúng3MP3; range1–10 →ZIP1/2/10 +7chương bỏqua; hashesMP3 trongZIP bằng nguồn; range thiếuhoàntoàn vôhiệu download; range ngược báolỗi; xóa nguồn saupreview chặn prepare; không phát sinh jobTTS;390px khôngoverflow/lỗiJS/requestngoàilocal. Ảnh range-mobile.png đãxem; báo cáo browser-report.json, selected.zip/range.zip vàscript verify-browser.cjs trongthưmụccùngtên. MP3dùng âm tonefixture, không nghiệmthu chấtlượnggiọng.

Chạy lại: restartlauncher, mởtruyện → tickchương ởcáctrang hoặcnhập khoảng trong Tải audio hàng loạt → Kiểmtra audio → Tải N MP3 (ZIP). Suite api/.venv/bin/python -m api.check; testcase test_audio_downloads.py. Scriptbrowser dùngPlaywright/Edge quaNODE_PATH,8100/8101,kho riêngtimestamp vàdừngprocessdo nó tạo. Dữliệu sảnxuất/input/output khôngbị thay.
