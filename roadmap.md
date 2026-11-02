# Roadmap novel2voice — từ v1.0 đến v2.0

Ngày chốt kế hoạch: 28/10/2026. Đây là kế hoạch phát triển; chỉ v1.0 là hiện trạng đã có. Các lệnh và cấu trúc được nhắc tới cho phiên bản sau là thiết kế dự kiến.

## 1. Đích đến và nguyên tắc

**URL truyện → lấy chương → làm sạch → dịch nếu cần → tạo audio → đóng gói tập → render video → duyệt → xuất bản YouTube.**

Mỗi phiên bản phải có một luồng sử dụng hoàn chỉnh, chạy riêng được và có điều kiện nghiệm thu. Tiếp tục dùng Python, SQLite và file trên máy; tận dụng các module hiện có. Chỉ tách thêm module khi có chức năng cần dùng, không viết lại toàn bộ hệ thống.

Phạm vi A–Z đầu tiên: một website, một bộ truyện, một giọng đọc, một mẫu video bằng ảnh có sẵn và một kênh YouTube. Nội dung tiếng Việt được bỏ qua bước dịch.

Chưa gắn lịch phát hành: thời gian phụ thuộc nguồn web được chọn, tài nguyên chạy TTS và nhu cầu biên tập. Ước lượng sau khi tách task của từng version; không xem số version là cam kết thời gian.

## 2. Big picture theo phiên bản

| Version | Mục tiêu | Đầu ra người dùng nhận được | Phụ thuộc |
|---|---|---|---|
| **1.0 — Hiện tại** | Tạo audiobook từ TXT | MP3 chương/tệp gộp, checkpoint TTS | Đã có |
| **1.1** | Web app gồm app/API và quản lý bộ truyện | Thao tác dịch/TTS/ghép/import/cấu hình/theo dõi qua trình duyệt | 1.0 |
| **1.2** | Dịch có thể tiếp tục và biên tập | Bản dịch có kiểm tra, lịch sử và audio cập nhật đúng phần thay đổi | 1.1 |
| **1.3** | Lấy truyện từ một website | Chương gốc được đồng bộ vào bộ truyện | 1.1; tích hợp đầy đủ với 1.2 |
| **1.4** | Quản lý tập audiobook | Audio tập, danh sách chương và timestamp | 1.1–1.2; dùng được với nguồn 1.3 |
| **1.5** | Sản xuất video | Video, thumbnail và metadata sẵn sàng upload | 1.4 |
| **1.6** | Xuất bản có kiểm soát | Video trên YouTube, lịch sử upload và chống trùng | 1.5 |
| **2.0** | Tự động vận hành toàn chuỗi | Tự đồng bộ, sản xuất, xếp lịch và báo lỗi | 1.1–1.6 |

**Các cột mốc:** 1.2 = lõi nội dung/audio đáng tin cậy; 1.4 = sản xuất audiobook có quản lý tập; 1.6 = đi hết A–Z với thao tác chủ động và bước duyệt; 2.0 = tự chạy theo lịch và chính sách đã cấu hình.

## 3. v1.0 — Mốc xuất phát

Đóng dấu hiện trạng làm v1.0, không coi các tính năng tương lai là đã hoàn thành.

Đã có:

- CLI: `process`, `translate`, `tts`, `doctor`, `status`, `voices`.
- Dịch EN → VI qua API, glossary và chia đoạn cơ bản.
- Mã tích hợp VieNeu, Edge-TTS, OpenAI TTS và Piper.
- TTS từng chương, batch, sắp xếp tự nhiên và ghép MP3.
- SQLite checkpoint cho job/đoạn TTS; retry, resume, checksum và ghi file cuối sau kiểm tra.
- 20 bài kiểm thử đã chạy thành công tại thời điểm đánh giá.

Giới hạn mang sang backlog: chưa quản lý bộ truyện/kênh; dịch chưa có checkpoint; thư mục đầu vào chưa quét đệ quy; audio cũ chưa được tự nhận vào checkpoint; cấu hình/cài đặt provider chưa đồng bộ. Test hiện có chủ yếu dùng TTS giả, chưa thay thế nghiệm thu giọng thật.

## 4. v1.1 — Web app và nền tảng quản lý bộ truyện

**Kết quả:** sử dụng các action hiện tại qua trình duyệt, có quản lý truyện/chương, import TXT/audio cũ, cấu hình riêng và job nền có tiến độ/dừng/chạy tiếp.

**Yêu cầu chi tiết và backlog:** [v1.1 requirements](docs/v1.1-requirements.md). **Task thực thi:** [34 task nhỏ, mỗi task có output và flow verify](docs/tasks/v1.1/README.md).

Kiến trúc tách `app/` (giao diện) và `api/` (HTTP API, job/worker, dữ liệu); tận dụng lõi Python `src/`. Bản đầu chạy local, một người dùng, SQLite và một worker cho job nặng. CLI giữ tương thích. Stack đã chốt: Vue 3 + Vite + Tailwind CSS, FastAPI, SQLite + SQLModel, uv và pnpm; xem [ADR 002](docs/decisions/002-vue-fastapi-sqlmodel.md).

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V11-01 | Cài đặt provider, doctor, smoke test hiện trạng | Lõi chạy được; xác nhận VieNeu thật |
| V11-02 | Truyện/chương/artifact, migration và backup | Hai truyện độc lập; giữ dữ liệu/checkpoint cũ |
| V11-03 | Service cấu hình và API contract | Cấu hình hiệu lực/snapshot rõ ràng; request/response thống nhất |
| V11-04 | Import TXT đệ quy và MP3 cũ | Preview/confirm, chống trùng, ghi nguồn gốc và ánh xạ |
| V11-05 | Queue/worker cho dịch, TTS, process và ghép | Không chặn HTTP; dừng/tiếp tục, phục hồi restart, chống chạy trùng |
| V11-06 | API nghiệp vụ, trạng thái và media | Validation, bảo vệ local, stream/tải TXT/MP3 bằng ID |
| V11-07 | Khung app và API client | Điều hướng/form/bảng tiếng Việt, loading/rỗng/lỗi |
| V11-08 | UI truyện/chương/import/cấu hình | Thao tác dữ liệu thực tế hoàn toàn qua web |
| V11-09 | UI tác vụ/tiến độ/báo cáo/audio | Chạy action hiện tại, nghe/tua/tải, theo dõi sau reload |
| V11-10 | Nghiệm thu tích hợp và tài liệu | Qua kịch bản trong requirements; app gọi API thật |

**Nghiệm thu version:** import truyện và audio cũ, cấu hình, dịch/TTS/process/ghép qua web; dừng/chạy tiếp và mở lại trình duyệt không mất tiến độ. Nghiệm thu giọng thật, migration/restore và tương thích CLI.

**Giới hạn:** checkpoint dịch từng đoạn và biên tập nâng cao thuộc v1.2; v1.1 phải đưa khả năng dịch hiện tại lên web, lưu kết quả từng bước và báo rõ giới hạn khi retry. Queue local tối thiểu có ngay; điều phối toàn chuỗi theo lịch thuộc v2.0.

**Chưa làm:** fetch web, video, YouTube, đa người dùng và triển khai Internet.

## 5. v1.2 — Dịch bền vững và kiểm soát nội dung

**Kết quả:** dịch truyện dài có thể dừng/chạy tiếp, sửa bản dịch và cập nhật audio liên quan.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V12-01 | Checkpoint/retry/cache cho từng đoạn dịch; tách giới hạn chia đoạn dịch và TTS | Lỗi giữa chương rồi chạy tiếp không gọi lại đoạn dịch đã hoàn thành hợp lệ |
| V12-02 | Lưu phiên bản prompt/model/glossary, bản gốc và bản dịch | Thay cấu hình tạo phiên mới; không mất bản dịch đã biên tập |
| V12-03 | Hồ sơ truyện, tên riêng/xưng hô, glossary theo nội dung và ngữ cảnh có giới hạn | Kiểm chứng bằng bộ chương mẫu; lưu được ngữ cảnh đã dùng để tái hiện lỗi |
| V12-04 | Kiểm tra phản hồi rỗng, lý do kết thúc, dấu hiệu cắt/thiếu và lệch ngôn ngữ | Các ca lỗi mẫu bị chặn hoặc chuyển cần duyệt; không coi tỷ lệ độ dài là bằng chứng dịch đầy đủ |
| V12-05 | Luồng sửa/duyệt bản dịch và đánh dấu audio cũ khi nội dung thay đổi | Bản dịch đã duyệt không bị ghi đè tự động; tạo lại audio chịu ảnh hưởng, tái dùng cache còn phù hợp |
| V12-06 | Nối lại `process` theo trạng thái từng bước; ghi thời gian/token và chi phí ước tính khi đủ dữ liệu | Chạy lại bỏ qua bước hợp lệ; thiếu dữ liệu giá thì không hiển thị chi phí như số chính xác |

**Nghiệm thu version:** một nhóm chương EN được dịch, có lỗi giữa chừng, tiếp tục được; sửa một chương rồi chỉ cập nhật kết quả phụ thuộc. Người đọc duyệt mẫu về nội dung và tính nhất quán.

**Chưa làm:** cam kết tự động xác nhận bản dịch đúng hoàn toàn; tối ưu nhiều nhà cung cấp dịch.

## 6. v1.3 — Lấy truyện từ một website

**Kết quả:** nhập URL, xem trước và đồng bộ chương vào mô hình dữ liệu hiện có.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V13-01 | Chọn website đầu tiên, định nghĩa adapter và lưu mẫu HTML kiểm thử | Xử lý được trang truyện, mục lục, chương và phân trang của nguồn đã chọn |
| V13-02 | Lấy mục lục; ánh xạ chương theo định danh nguồn | Thứ tự ổn định; phát hiện chương trùng/thiếu và thay đổi URL |
| V13-03 | Trích xuất/làm sạch; giữ bản gốc và metadata nguồn | Bộ mẫu không chứa menu/quảng cáo; giữ được nội dung và đoạn hội thoại |
| V13-04 | Retry, giới hạn tốc độ, timeout và tiếp tục tải | Lỗi một chương không làm mất chương đã tải; lần sau chỉ xử lý phần còn thiếu |
| V13-05 | Đồng bộ chương mới/thay đổi và chuyển vào dịch/TTS | Chạy lại không nhân đôi; thay đổi nguồn cần được đối chiếu trước khi thay bản đã biên tập |

**Nghiệm thu version:** đồng bộ cùng truyện hai lần không trùng, thêm chương mới chỉ nhập phần mới; một chương nguồn thay đổi được báo rõ. Chương VI đi thẳng TTS, chương EN qua dịch.

**Chưa làm:** crawler mọi website, vượt cơ chế chặn truy cập, chạy lịch tự động.

## 7. v1.4 — Quản lý tập audiobook

**Kết quả:** đóng gói các chương thành tập có danh tính, thứ tự và timestamp ổn định.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V14-01 | Mô hình tập và manifest: danh sách/phiên bản chương, thứ tự, cấu hình | Một tập tái hiện được chính xác từ manifest; không dùng audio đã lỗi thời |
| V14-02 | Chia tập theo số chương, chọn tay hoặc thời lượng mục tiêu | Xem trước trước khi tạo; không cắt giữa chương; báo khi một chương vượt mục tiêu |
| V14-03 | Ghép tập; mở đầu/kết thúc/khoảng nghỉ tùy chọn; timestamp | Timestamp tính cả nội dung chèn; số đoạn, thứ tự và thời lượng được kiểm tra |
| V14-04 | Trạng thái và phiên bản tập; cố định tập đã xuất bản | Chương mới không tự đổi tập đã chốt; sửa chương khiến tập liên quan cần cập nhật |

**Nghiệm thu version:** tạo nhiều tập từ bộ chương có sẵn; ghép lỗi rồi chạy tiếp không tạo lại audio chương; xuất manifest và timestamp cho từng tập.

**Chưa làm:** render video, tối ưu âm thanh nâng cao hoặc tự chia giữa chương.

## 8. v1.5 — Video và bộ nội dung xuất bản

**Kết quả:** mỗi tập tạo ra video, thumbnail và metadata có thể upload thủ công.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V15-01 | Hồ sơ kênh tối thiểu: tên, mẫu hình, font, mẫu tiêu đề/mô tả | Cấu hình tách khỏi bộ truyện; có xem trước nội dung tập trước render |
| V15-02 | Render FFmpeg: audio + ảnh nền + tiêu đề | Video có hình/âm thanh, đúng tỷ lệ và thời lượng; tiếng Việt hiển thị đúng |
| V15-03 | Thumbnail và metadata theo mẫu; đưa timestamp chương vào mô tả | Bộ file xuất ra có tên/đường dẫn nhất quán; kiểm tra trường bắt buộc |
| V15-04 | Job render, cache, kiểm tra và xuất bộ file | Render lỗi không thay file hợp lệ; chạy lại tái dùng video khi đầu vào không đổi |

**Nghiệm thu version:** tạo một video dài thực tế, xem/nghe các mốc đầu–giữa–cuối và chuyển chương; bộ file đủ để upload thủ công.

**Chưa làm:** tạo ảnh AI, nhiều cảnh, phụ đề đồng bộ, tự đăng YouTube.

## 9. v1.6 — Xuất bản YouTube có kiểm soát

**Kết quả:** từ tập đã duyệt, upload và theo dõi kết quả xuất bản trên một kênh.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V16-01 | Kết nối tài khoản/kênh, lưu thông tin xác thực riêng khỏi cấu hình nội dung | Kiểm tra đúng kênh đích; kết nối lại khi hết hạn; không ghi token vào log |
| V16-02 | Upload có thể tiếp tục, lưu phiên upload và video ID | Ngắt mạng rồi tiếp tục; khôi phục được khi tiến trình chết giữa upload và lưu kết quả |
| V16-03 | Gắn thumbnail/metadata, chế độ hiển thị và lịch xuất bản | Hiển thị bản xem trước; đối chiếu trạng thái xử lý thực tế từ YouTube |
| V16-04 | Bước duyệt và chống upload trùng theo tập/phiên bản/kênh | Chạy lại không tạo video mới ngoài ý muốn; kết quả chưa rõ phải đối soát trước retry |
| V16-05 | Lịch sử xuất bản và xử lý lỗi/quota | Có URL/ID, bước lỗi và hành động tiếp tục; không đánh dấu thành công chỉ vì đã gửi yêu cầu |

**Nghiệm thu version:** upload thử ở chế độ riêng tư, ngắt/chạy tiếp, chạy lại kiểm tra không trùng; sau khi duyệt mới thử lịch xuất bản theo cấu hình.

**Chưa làm:** tự duyệt nội dung, tối ưu tăng trưởng kênh hoặc quản lý nhiều kênh nâng cao. Khi triển khai phải đối chiếu yêu cầu API và quota tại thời điểm đó.

## 10. v2.0 — Vận hành tự động toàn chuỗi

**Kết quả:** cấu hình một lần, hệ thống theo dõi chương mới và tự đi qua các bước trong phạm vi đã cho phép.

| Task | Phạm vi có thể giao riêng | Điều kiện nghiệm thu |
|---|---|---|
| V20-01 | Hàng đợi bền vững, phụ thuộc job, retry có giới hạn và phục hồi sau restart | Không mất/nhân đôi công việc; lỗi bước trước chặn đúng bước sau |
| V20-02 | Lịch đồng bộ và quy tắc đủ điều kiện tạo tập | Không tạo trùng tập; chưa đủ chương thì chờ; cấu hình được xử lý tập cuối |
| V20-03 | Giới hạn CPU/RAM, số job, token/ngân sách và dung lượng | Hết giới hạn thì dừng nhận việc phù hợp và báo lý do, không làm hỏng kết quả |
| V20-04 | Chính sách duyệt, tự xuất bản và thông báo | Mặc định giữ bước duyệt; tự xuất bản chỉ khi bật rõ; chỉ báo sự kiện cần chú ý |
| V20-05 | Mở rộng web app v1.1 để giám sát toàn chuỗi, tập/video/xuất bản | Thấy phụ thuộc, bước lỗi, chính sách duyệt và lịch; chạy lại đúng ràng buộc trạng thái |
| V20-06 | Backup/restore, lưu trữ, dọn cache và nhật ký vận hành | Khôi phục thử thành công; không xóa nguồn hoặc artifact còn được tham chiếu |

**Nghiệm thu version:** chạy thử có giám sát tối thiểu 7 ngày với một nguồn/truyện/kênh; có chương mới, lỗi mạng và restart; không mất chương, không đăng trùng, tiếp tục được và tôn trọng bước duyệt/ngân sách. Nếu không có chương mới thực tế, bổ sung dữ liệu mô phỏng để kiểm tra luồng.

**Sau 2.0:** thêm adapter website, nhiều kênh, giọng/nhà cung cấp, ảnh AI, phụ đề, mẫu video và nhiều máy xử lý theo nhu cầu thực tế.

## 11. Phụ thuộc và cách chia việc

Luồng triển khai chính: **1.0 → 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 2.0**.

Có thể phát triển nhánh sau khi hợp đồng dữ liệu v1.1 ổn định:

- Adapter web v1.3 song song với dịch v1.2; tích hợp sau khi cả hai nghiệm thu.
- Quản lý tập v1.4 dùng TXT/audio sẵn có, không bắt buộc chờ nguồn web.
- Mẫu video và thumbnail có thể thử bằng tập mẫu trong khi hoàn thiện v1.4.
- Khảo sát kết nối YouTube trong v1.5; tích hợp xuất bản sau khi bộ file đầu ra ổn định.
- Giữ xử lý thủ công qua CLI làm đường kiểm tra cho từng bước, kể cả sau khi có dashboard.

Không dùng số version làm lý do ép tính năng chưa liên quan vào cùng một đợt. Chỉ tách làm song song khi đã thống nhất định danh, cấu hình và manifest đầu vào/đầu ra.

### Mẫu task triển khai

Mỗi dòng có mã task ở trên là một nhóm việc. Trước khi giao, tách thành task nhỏ đủ để review riêng, theo mẫu:

```text
ID / Version:
Mục tiêu và tình huống người dùng:
Phụ thuộc:
Đầu vào / đầu ra:
Phạm vi thực hiện:
Ngoài phạm vi:
Điều kiện nghiệm thu:
Ca lỗi và cách khôi phục cần kiểm tra:
Migration / tương thích dữ liệu cũ (nếu có):
Bằng chứng kiểm tra / hướng dẫn chạy thử:
```

Task thông thường nên hoàn thành trong khoảng 0,5–2 ngày làm việc; việc lớn hơn cần chia nhỏ. Đây là hướng dẫn chia việc, không phải ước lượng tổng thời gian version.

### Điều kiện hoàn thành chung cho mỗi version

- Luồng chính và các ca lỗi quan trọng đã được kiểm tra; smoke test dịch vụ/model thật ở phần tích hợp thay đổi.
- Có bằng chứng nghiệm thu từ bộ dữ liệu mẫu cố định và một mẫu sử dụng thực tế.
- Chạy lại không ghi đè bản biên tập hoặc tạo trùng đầu ra ngoài ý muốn.
- Dữ liệu cũ đọc được hoặc có migration/backup được kiểm chứng.
- CLI, cấu hình mẫu, README và hạn chế đã biết được cập nhật.
- Ghi release notes và tạo tag khi thực sự phát hành; số version trong roadmap không tự tạo Git tag.

## 12. Thứ tự bắt đầu đề xuất

1. V11-01: đồng bộ cài đặt và xác nhận lõi/VieNeu thật.
2. V11-02: chốt dữ liệu truyện/chương/artifact, migration và backup.
3. V11-03: chốt cấu hình, service dùng chung và hợp đồng app/API.
4. V11-04/05/07: triển khai import, job nền và khung app theo hợp đồng.
5. V11-06/08/09: tích hợp API và các màn hình thao tác thật.
6. V11-10: nghiệm thu web app v1.1 trước khi mở rộng dịch ở v1.2.

Quyết định cần chốt đúng lúc: stack app/API đã chốt tại ADR 002; website đầu tiên trước V13-01; quy tắc chia tập trước V14-02; mẫu hình/kênh trước V15-01; tài khoản/kênh và chính sách duyệt trước v1.6.
