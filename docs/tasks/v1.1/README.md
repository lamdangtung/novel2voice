# v1.1 — Task triển khai và flow nghiệm thu

Trạng thái: **T01–T03 đã được chấp nhận; T04–T33 đã nghiệm thu kỹ thuật tự động; T34 đang tổng nghiệm thu, chưa phát hành. VieNeu thật đã tạo/phát được; chất lượng giọng và dịch API thật chưa được người dùng nghiệm thu**. Ngày chia task: 28/10/2026.

Bàn giao hiện có: [T01 — app/API local](evidence/T01.md), [T02 — workspace nghiệm thu offline](evidence/T02.md), [T03 — kiểm tra môi trường](evidence/T03.md).

Nguồn phạm vi: [requirements v1.1](../../v1.1-requirements.md). Nguồn UI/UX: [mock đã review](../../ui/v1.1/README.md). Bản mock dùng để tham khảo giao diện; mọi task chức năng dưới đây phải chạy với API và dữ liệu thật trong workspace kiểm thử, trừ chế độ giả lập được chỉ rõ.

## 1. Quy tắc chia và hoàn thành task

Người dùng đã yêu cầu tự động triển khai toàn backlog, không dừng chờ sau từng task. Task có flow và bằng chứng kiểm tra đạt được đánh dấu Done với verification=agent_verified; phân biệt với user_accepted. Các giới hạn/việc chưa nghiệm thu giọng thật vẫn được ghi rõ.

- Mỗi task giao **một khả năng có thể dùng và nghiệm thu riêng**. Bao gồm app/API/service cần thiết cho khả năng đó, thay vì hoàn thành một loạt API rồi mới có UI để kiểm tra.
- “Độc lập” nghĩa là có output, flow và tiêu chí đạt riêng **sau khi các phụ thuộc đã hoàn thành**; không có nghĩa task không phụ thuộc nhau.
- Task nền phải có trình kiểm tra/lệnh thao tác cụ thể trong hướng dẫn nghiệm thu, có output quan sát được. Không chấp nhận chỉ giao schema, lớp service hoặc code chưa có cách chạy lại.
- Mỗi task khi bàn giao phải ghi chính xác lệnh khởi động, đường dẫn màn hình, dữ liệu đầu vào và kết quả mong đợi. Các thao tác dưới đây là thiết kế dự kiến, chưa phải hướng dẫn cho phần mềm hiện tại.
- Mục tiêu một task khoảng 0,5–2 ngày; nếu flow vẫn quá lớn, chia tiếp nhưng mỗi task con phải giữ được một output chạy thử. Không coi đây là ước lượng lịch phát hành.
- Không làm tính năng ngoài phạm vi để “chuẩn bị cho tương lai”. Không gọi dịch vụ tính phí trong nghiệm thu mặc định.
- Chỉ đánh dấu hoàn thành sau khi chạy flow chính, flow lỗi liên quan và chạy lại. Test tự động tập trung vào bảo toàn dữ liệu, trạng thái và hợp đồng; chỉnh UI nhỏ chỉ cần kiểm tra phù hợp.

### Gói bàn giao bắt buộc cho từng task

1. Code tích hợp và ghi chú API/config/migration thay đổi nếu có.
2. Hướng dẫn chạy lại tại `docs/tasks/v1.1/evidence/Txx.md`, nêu môi trường/commit đã thử, fixture, bước thao tác và output.
3. Bằng chứng thích hợp: ảnh màn hình, response, job ID, checksum hoặc báo cáo test; không chứa secret.
4. Kết luận đạt/chưa đạt, giới hạn còn lại và cách reset dữ liệu kiểm thử của task.

Thư mục evidence và fixture sẽ được tạo trong task tương ứng; tài liệu kế hoạch này không coi chúng là kết quả đã có.

## 2. Workspace nghiệm thu dùng chung

T02 cung cấp bộ mẫu cố định, không dùng trực tiếp kho `input/`, `output/` thật:

- Hai truyện A/B, cùng số chương để kiểm tra cách ly dữ liệu.
- TXT VI có chương 1, 2, 10 và cấu trúc thư mục con; TXT EN ngắn.
- File rỗng, encoding lỗi, số chương trùng, tên không nhận diện được và bản TXT đã sửa.
- Audio ngắn hợp lệ, file hỏng và tên MP3 mơ hồ; sinh bằng FFmpeg để không phụ thuộc dịch vụ TTS.
- Provider kiểm thử có output audio thật, ghi nhật ký số lần gọi, cho chủ động lỗi ở đoạn/chương và giữ tác vụ đủ lâu để thử dừng/restart.
- Translator kiểm thử có kết quả xác định, đếm số lần gọi và chủ động lỗi. Luôn gắn nhãn “chế độ kiểm thử”, không đưa vào danh sách provider sản xuất thông thường.
- Công cụ tạo/reset workspace riêng; từ chối reset đường dẫn dữ liệu sản xuất. Mỗi flow chỉ rõ dữ liệu của task cần reset, không bắt làm lại toàn bộ version.

Các ca TTS/API thật chạy riêng ở T31/T34 và ghi provider/model/giọng đã thử. Test giả lập không được dùng làm bằng chứng chất lượng giọng/dịch thật.

## 3. Các đợt bàn giao có thể demo

| Đợt | Task | Demo cuối đợt |
|---|---|---|
| A — Mở được ứng dụng | T01–T03 | Mở web, thấy kết nối API, chạy kiểm tra môi trường |
| B — Quản lý nội dung | T04–T10 | Tạo truyện, import TXT, tìm/chọn/xem/tải chương |
| C — Cấu hình và audio cũ | T11–T14, T26 | Cấu hình truyện, import MP3, nghe/tua/tải |
| D — Tạo audio có thể phục hồi | T15–T21 | Tạo TTS, batch, dừng/tiếp tục, lỗi/restart rồi chạy lại |
| E — Đủ các action v1.0 | T22–T25 | Dịch, process, ghép, thử giọng qua web |
| F — Hoàn thiện vận hành | T27–T34 | Bảo vệ dữ liệu, tương thích, đóng gói và nghiệm thu thật |

Đây là thứ tự mặc định. T26/T28/T29 có thể làm sớm khi phụ thuộc đã đủ; các bảo vệ cơ bản phải có ngay từ endpoint đầu tiên, không chờ đợt F.

## 4. Task chi tiết

### T01 — Khởi động app và API local

**Nhóm gốc:** V11-03/06/07. **Phụ thuộc:** không.

**Output:** `app/` và `api/` chạy cùng một luồng khởi động; khung sidebar theo mock, endpoint health, API client và trang lỗi kết nối. Dùng Vue 3/Vite/Tailwind (`<script setup>`), FastAPI có Swagger/OpenAPI, uv/pnpm và lockfile theo [ADR 002](../../decisions/002-vue-fastapi-sqlmodel.md). API bind loopback, kiểm tra Host/Origin và quy tắc lỗi ngay từ đầu.

**Flow verify:** khởi động → mở Tổng quan → thấy API đã kết nối → tắt API → tải lại → thấy lỗi và nút thử lại → bật API → thử lại thành công.

**Đạt / chạy lại:** chạy trên máy local theo hướng dẫn, không cần chỉnh code; không hiện dữ liệu thống kê giả như thật. Chưa có database/worker cũng phải mở được shell và báo đúng trạng thái.

### T02 — Bộ dữ liệu và chế độ nghiệm thu lặp lại

**Nhóm gốc:** V11-10. **Phụ thuộc:** T01.

**Output:** fixture và công cụ tạo/reset workspace theo mục 2; màn hình đánh dấu chế độ kiểm thử và nơi xem kết quả provider/translator giả lập. Có một lệnh self-check sinh audio, kiểm tra bằng ffprobe và in số lần gọi giả lập.

**Flow verify:** tạo workspace → self-check với đoạn VI và EN → thấy MP3 hợp lệ/bản dịch mẫu/nhật ký → chạy reset → self-check lại ra cùng kết quả logic.

**Đạt / chạy lại:** không gọi mạng/model thật, không sửa kho thật; cố reset đường dẫn sản xuất bị từ chối. Task sau có thể chủ động tạo lỗi/delay mà không sửa mã provider sản xuất.

### T03 — Kiểm tra môi trường trên web

**Nhóm gốc:** V11-01/06/08. **Phụ thuộc:** T01, T02.

**Output:** trang Môi trường gọi doctor thật, báo FFmpeg/ffprobe, dependency, model/config và trạng thái key đã cấu hình; lỗi có hướng xử lý.

**Flow verify:** mở Môi trường → chọn provider → kiểm tra → thấy thành phần sẵn sàng/thiếu → dùng fixture thiếu dependency hoặc model → kiểm tra lại → thấy lỗi đúng thành phần.

**Đạt / chạy lại:** không nạp/tải model, không gọi mạng; báo đúng sau khi cấu hình được sửa. Chưa có thao tác thử giọng ở task này.

### T04 — Schema dữ liệu và nâng cấp checkpoint v1.0

**Nhóm gốc:** V11-02. **Phụ thuộc:** T02.

**Output:** mô hình truyện/chương/artifact/job bằng SQLModel trên SQLite, session/repository và schema version; migration dùng bản sao fixture checkpoint v1.0, có backup trước nâng cấp và trình kiểm tra báo số bản ghi/checksum trước–sau. Chốt cách tham chiếu checkpoint cũ mà không tự gán MP3 chưa xác minh vào chương.

**Flow verify:** sao chép fixture v1.0 → chạy migration → xem báo cáo dữ liệu/checkpoint/audio giữ nguyên → chạy migration lần hai → báo không cần thay đổi → gây lỗi nâng cấp trên bản sao khác → khôi phục backup.

**Đạt / chạy lại:** không sửa DB/audio gốc; không mất bản ghi hoặc coi audio cũ tự động khớp TXT. Chưa cần UI quản lý truyện để nghiệm thu task nền này.

### T05 — Tạo, xem và sửa bộ truyện

**Nhóm gốc:** V11-02/06/08. **Phụ thuộc:** T01, T04.

**Output:** thư viện gọi API thật; tạo/sửa tên, ngôn ngữ; ID và vùng lưu riêng. Có trạng thái thư viện rỗng và validation.

**Flow verify:** tạo truyện A và B → sửa tên A → refresh → mở từng truyện → restart API → mở lại thư viện.

**Đạt / chạy lại:** thông tin tồn tại sau restart, ID không đổi; tên rỗng bị báo lỗi; bấm lặp cùng request không tạo ngoài ý muốn. Chưa có xóa dữ liệu vật lý.

### T06 — Upload TXT với xem trước và xác nhận

**Nhóm gốc:** V11-04/06/08. **Phụ thuộc:** T02, T05.

**Output:** upload một/nhiều TXT, phiên import preview/confirm, ánh xạ số chương và copy vào vùng quản lý kèm provenance. Màn hình kết quả import tối thiểu hiển thị chương đã nhập.

**Flow verify:** mở A → chọn TXT chương 1/2/10 và file rỗng/encoding lỗi → xem trước → bỏ các file lỗi → xác nhận → thấy ba chương đúng thứ tự → refresh → mở lại kết quả.

**Đạt / chạy lại:** nguồn còn nguyên; hủy preview không tạo chương; xác nhận cùng phiên hai lần không nhập trùng. Giới hạn upload và kiểm tra đường dẫn áp dụng ngay, không chờ T29.

### T07 — Nhập thư mục local và thư mục con

**Nhóm gốc:** V11-04/06/08. **Phụ thuộc:** T06.

**Output:** chọn thư mục trong vùng server được cho phép, tùy chọn đệ quy, dùng chung preview/confirm của TXT.

**Flow verify:** chọn fixture thư mục có TXT ngoài cùng và trong `ep/` → xem trước khi tắt đệ quy → bật đệ quy → thấy thêm đúng chương → xác nhận → lặp trên workspace đã reset.

**Đạt / chạy lại:** không nhầm upload từ browser với đường dẫn server; thư mục ngoài vùng cho phép/symlink thoát vùng bị từ chối, không đọc nội dung trước khi báo lỗi.

### T08 — Xử lý trùng và cập nhật TXT đã nhập

**Nhóm gốc:** V11-04/08. **Phụ thuộc:** T06, T07.

**Output:** preview nhận diện giống hệt/trùng số/đã đổi; chọn bỏ qua hoặc xác nhận cập nhật; lưu bản cũ và dấu vết nội dung, trả trạng thái phụ thuộc cần cập nhật.

**Flow verify:** import cùng bộ TXT → thấy không có chương mới → thay TXT chương 2 → preview → chọn cập nhật → xem checksum/phiên bản thay đổi → thay nguồn sau preview nhưng trước confirm → bị yêu cầu xem trước lại.

**Đạt / chạy lại:** không nhân đôi; không tự ghi đè bản cũ; thay đổi nội dung được phát hiện bằng hash. T14/T17 sẽ kiểm tra tiếp việc đánh dấu audio cũ trên UI.

### T09 — Bảng chương, tìm/lọc và chọn phạm vi

**Nhóm gốc:** V11-08. **Phụ thuộc:** T06.

**Output:** bảng chương theo mock, phân trang API, tìm số/tên, lọc trạng thái, chọn nhiều/khoảng chương; hiển thị số lượng chọn và phạm vi chọn tất cả rõ ràng.

**Flow verify:** nhập dữ liệu đủ nhiều trang → tìm chương 10 → đổi bộ lọc → chọn vài chương ở hai trang → xem danh sách ID đã chọn → bỏ chọn và chọn khoảng 1–10.

**Đạt / chạy lại:** đúng thứ tự tự nhiên; không lẫn truyện; chọn tất cả chỉ theo phạm vi được UI ghi rõ. Chưa cần tạo job để kiểm tra selection, danh sách lựa chọn phải xem được.

### T10 — Xem và tải nội dung chương

**Nhóm gốc:** V11-06/08. **Phụ thuộc:** T09.

**Output:** chi tiết chương hiển thị nội dung gốc/bản dịch nếu có, metadata và tải TXT qua artifact ID.

**Flow verify:** bấm tên chương → đọc nội dung → tải TXT → đối chiếu file nhập → mở chương khác/chương không tồn tại.

**Đạt / chạy lại:** giữ tiếng Việt, xuống dòng, đúng chương; không có bản dịch thì hiện rỗng có giải thích; ID sai trả lỗi phù hợp. Có thể chạy lại sau refresh.

### T11 — Lưu cấu hình workspace và riêng từng truyện

**Nhóm gốc:** V11-03/08. **Phụ thuộc:** T03, T05.

**Output:** form provider/giọng, chunk, concurrency, retry, cleanup, model dịch; API capabilities để hiện đúng tùy chọn và xem cấu hình hiệu lực. Tách nơi lưu mặc định với override theo truyện.

**Flow verify:** đặt mặc định workspace → cấu hình A dùng giọng riêng → B kế thừa mặc định → reload/restart → thay mặc định → A giữ override, B cập nhật kế thừa → gửi giá trị batch/retry không hợp lệ.

**Đạt / chạy lại:** API và UI cùng kiểm tra; không quảng cáo tùy chọn provider không hỗ trợ; xem được giá trị và nguồn kế thừa. Chưa xử lý secret trên form.

### T12 — Glossary riêng cho truyện

**Nhóm gốc:** V11-03/08. **Phụ thuộc:** T06, T11.

**Output:** upload/xem/thay glossary CSV theo truyện, validation cột/dòng và phiên bản/hash. Không cần editor từng ô ở v1.1.

**Flow verify:** A nhập glossary hợp lệ → xem thuật ngữ → B vẫn dùng glossary riêng/mặc định → upload CSV lỗi → thấy dòng lỗi → thay bản hợp lệ → restart và mở lại.

**Đạt / chạy lại:** lỗi không thay glossary đang dùng; lưu nguồn/phiên bản; T22 kiểm chứng glossary thực sự đi vào request dịch.

### T13 — Import MP3 cũ và xác nhận ánh xạ

**Nhóm gốc:** V11-04/06/08. **Phụ thuộc:** T08, T10.

**Output:** upload MP3 hoặc quét thư mục cho phép; preview đề xuất chương, sửa mapping, xác nhận, kiểm tra bằng ffprobe và lưu checksum/provenance. Cho biết mỗi chương đang chọn audio nào khi có nhiều bản.

**Flow verify:** nhập MP3 hợp lệ/hỏng/mơ hồ → đổi ánh xạ mơ hồ → xác nhận → thấy audio nhập trước ở đúng chương → nhập lại → không trùng → cập nhật TXT → audio hiện cần kiểm tra lại.

**Đạt / chạy lại:** không tự xác nhận mapping mơ hồ; nguồn không bị di chuyển; audio hỏng không được đánh dấu hợp lệ; nhãn nhập trước không tuyên bố đúng từng từ/cấu hình.

### T14 — Nghe, tua và tải audio

**Nhóm gốc:** V11-06/09. **Phụ thuộc:** T13.

**Output:** player trong truyện/chi tiết chương; stream HTTP Range và tải MP3 bằng ID, metadata thời lượng; truy cập đúng bản audio đang chọn.

**Flow verify:** mở chương có MP3 → play → tua giữa/cuối → đổi chương → tải MP3 → đối chiếu checksum → thử file mất/ID sai.

**Đạt / chạy lại:** browser nhận partial content khi tua; không đọc toàn MP3 vào RAM ở API; audio cũ có cảnh báo; mất file báo lỗi và không phát nhầm chương trước.

### T15 — Job nền tối thiểu có UI theo dõi

**Nhóm gốc:** V11-05/06/09. **Phụ thuộc:** T02, T04, T05.

**Output:** queue SQLite, một worker claim job, polling API và màn hình Công việc. Một action chỉ trong chế độ kiểm thử chạy provider giả lập lâu đủ để quan sát, chưa gọi TTS sản xuất.

**Flow verify:** tạo hai job thử → job đầu running, job sau queued → mở trang khác/reload → thấy job đầu vẫn chạy → xem kết quả sau hoàn thành.

**Đạt / chạy lại:** HTTP phản hồi nhanh trong lúc worker bận; state lưu thật; worker không claim một job hai lần. Chỉ cấp khả năng dừng/recover khi T19/T20 hoàn thành, không hiện nút hoạt động giả.

### T16 — Xem trước tác vụ và chốt cấu hình

**Nhóm gốc:** V11-03/05/09. **Phụ thuộc:** T09, T11, T15.

**Output:** wizard chọn action/phạm vi, resolve cấu hình và preview kế hoạch; confirm tạo job với snapshot immutable và request ID chống submit lặp. Lựa chọn action chưa triển khai phải hiện chưa khả dụng.

**Flow verify:** chọn chương → preview bằng action kiểm thử → đổi cấu hình truyện ở tab khác → confirm → hệ thống dùng snapshot đã xem hoặc yêu cầu xem lại, không âm thầm đổi → bấm confirm lặp.

**Đạt / chạy lại:** cùng request tạo một job; chương/nội dung thay đổi sau preview phải kiểm tra lại; hiển thị giữ/tái sử dụng/tạo lại/bị chặn. Không lấy API key vào snapshot công khai.

### T17 — Tạo audio cho một chương tiếng Việt

**Nhóm gốc:** V11-05/06/09. **Phụ thuộc:** T10, T14, T16.

**Output:** action TTS gọi lõi Python/checkpoint hiện có qua worker; tiến độ đoạn thực, audio artifact và report. Adapter cho provider sản xuất được nối nhưng nghiệm thu mặc định dùng provider kiểm thử.

**Flow verify:** chọn một chương VI → preview → chạy → xem đoạn đã hoàn thành → nghe/tải MP3 → chạy lại → thấy tái sử dụng, số lần gọi không tăng → thay TXT/giọng rồi preview lại.

**Đạt / chạy lại:** kết quả kiểm tra bằng ffprobe/hash, dữ liệu A/B cách ly; thay TXT/giọng đánh dấu output cũ và chỉ tái dùng cache phù hợp. Không ghi đè file cuối trước khi kiểm tra thành công. Giọng thật nghiệm thu ở T31.

### T18 — TTS batch và các chính sách xử lý

**Nhóm gốc:** V11-05/09. **Phụ thuộc:** T17.

**Output:** chọn nhiều/khoảng chương; thiếu audio/lỗi/cần cập nhật; resume/force, cleanup, retry, continue/fail-fast và giữ MP3 nhập trước; report theo chương.

**Flow verify:** batch có một chương đã xong, một MP3 cũ, một chương gây lỗi → preview → chạy continue → xem report → chạy lại với fail-fast → thử force và cleanup trên dữ liệu nhỏ.

**Đạt / chạy lại:** đúng kế hoạch bỏ qua/tạo lại, số lần retry đúng; force không âm thầm bỏ qua; cache được giữ/xóa theo chọn; không coi batch có lỗi là hoàn thành toàn bộ. Bằng chứng dùng nhật ký provider và file thực.

### T19 — Dừng an toàn và tiếp tục job

**Nhóm gốc:** V11-05/09. **Phụ thuộc:** T18.

**Output:** stop/resume API và nút UI; state stopping → stopped khi worker xác nhận; dừng job còn queued không gọi provider.

**Flow verify:** chạy batch kiểm thử có delay → dừng giữa đoạn/batch → thấy stopping rồi stopped → ghi số đoạn đã xong → tiếp tục → hoàn tất phần còn lại.

**Đạt / chạy lại:** không phát việc mới sau điểm dừng an toàn; không mất đoạn đã checkpoint; stop/resume lặp không tạo worker trùng. Khi chưa đủ tổng số đoạn, không hiển thị phần trăm giả.

### T20 — Phục hồi khi worker/API bị tắt đột ngột

**Nhóm gốc:** V11-05/09. **Phụ thuộc:** T19.

**Output:** phát hiện job orphan bằng cơ chế ownership/heartbeat hoặc tương đương, state interrupted, hướng tiếp tục; giữ queue và tránh nhận nhầm job của worker vẫn sống.

**Flow verify:** chạy batch dài → kill worker bằng hướng dẫn kiểm thử → restart → thấy interrupted và đoạn đã lưu → tiếp tục → restart API riêng khi worker vẫn chạy.

**Đạt / chạy lại:** không running vĩnh viễn, không double-run; job queued còn nguyên; API restart không đánh dấu nhầm worker còn sống. Các phần chưa checkpoint có thể phải làm lại và phải báo rõ.

### T21 — Retry đoạn lỗi và phục hồi audio hỏng

**Nhóm gốc:** V11-05/09/10. **Phụ thuộc:** T18, T20.

**Output:** hành động thử lại từ report; dùng checksum và validation để phát hiện cache/final hỏng; bảo toàn output cũ khi ghép lỗi.

**Flow verify:** gây lỗi đoạn thứ hai → thử lại → nhật ký chỉ gọi đoạn thiếu; làm hỏng MP3 cuối rồi chạy lại với cache còn giữ → rebuild; gây lỗi ghép → file cuối trước đó vẫn nguyên checksum.

**Đạt / chạy lại:** không cần xóa DB thủ công; chương lỗi/hoàn thành/chưa chạy có report đúng; không ghi đè audio hợp lệ bằng partial. Có thể lặp bằng fixture và lệnh inject lỗi đã tài liệu hóa.

### T22 — Dịch EN → VI trên web

**Nhóm gốc:** V11-05/06/09. **Phụ thuộc:** T10, T12, T16, T19, T26.

**Output:** action chỉ dịch; lưu original/translation riêng, xem/tải TXT, lỗi API và cảnh báo retry toàn chương. Job lưu model/prompt/glossary hash dùng thực tế.

**Flow verify:** truyện EN có glossary → preview → dịch bằng translator kiểm thử → xem/tải VI → đọc nhật ký xác nhận glossary → gây lỗi giữa chương → thử lại với cảnh báo → chạy lại chương đã có bản dịch.

**Đạt / chạy lại:** không ghi đè bản dịch sẵn có nếu chưa xác nhận; không đưa bản rỗng/bị lỗi thành hoàn thành; không hứa resume từng đoạn. Với dịch đang chạy, stop giữ trạng thái phù hợp dù provider chưa trả ngay.

### T23 — Dịch rồi tạo audio, tiếp tục đúng bước

**Nhóm gốc:** V11-05/09. **Phụ thuộc:** T17, T21, T22.

**Output:** action process, state từng bước; snapshot/hash liên kết bản dịch và TTS; tiếp tục TTS từ bản dịch đã lưu.

**Flow verify:** EN → process → cho dịch thành công nhưng TTS lỗi → xem bản dịch vẫn còn → sửa lỗi rồi tiếp tục → nghe MP3; kiểm tra số lần gọi translator không tăng.

**Đạt / chạy lại:** bản dịch thay đổi sau lỗi thì yêu cầu đối chiếu/chốt lại đầu vào; không gắn audio mới vào bản dịch cũ. Chạy lại toàn bộ chỉ khi người dùng chọn rõ.

### T24 — Ghép audio chương thành file chung

**Nhóm gốc:** V11-05/06/09. **Phụ thuộc:** T14, T16, T18.

**Output:** job ghép độc lập từ audio sẵn có; preview thứ tự và bản audio, MP3 gộp tải/nghe được, giữ file chương.

**Flow verify:** chọn chương 10/1/2 → preview 1 → 2 → 10 → ghép → kiểm tra thời lượng và nghe điểm nối → chạy lại → gây lỗi ghép rồi thử lại.

**Đạt / chạy lại:** không gọi TTS; audio thiếu/hỏng/cũ bị chặn hoặc phải giải quyết rõ trước chạy; tổng thời lượng trong dung sai; file gộp không trùng file chương. Chưa có quản lý tập/timestamp nâng cao của v1.4.

### T25 — Danh sách giọng và thử giọng ngắn

**Nhóm gốc:** V11-01/06/08/09. **Phụ thuộc:** T03, T11, T17, T26.

**Output:** capabilities/voices theo provider, ghi nguồn danh sách và trạng thái đã xác minh; nút thử giọng tạo job ngắn qua worker, không gắn kết quả vào chương truyện.

**Flow verify:** đổi provider → thấy giọng/tùy chọn phù hợp → nhập câu ngắn → preview ảnh hưởng mạng/model/chi phí nếu có → thử → nghe kết quả → thử giọng không hợp lệ.

**Đạt / chạy lại:** không gọi mạng/nạp model khi chỉ mở form; không ghi sample thành chương; thiếu dependency hoặc voice sai có lỗi dễ hiểu. Flow mặc định dùng provider kiểm thử; giọng thật ở T31.

### T26 — Trạng thái key và cấu hình kết nối an toàn

**Nhóm gốc:** V11-03/06/08. **Phụ thuộc:** T11.

**Output:** web thấy provider/model/endpoint đã giải quyết và trạng thái key có/không; secret lấy từ môi trường server. v1.1 không cần form nhập key: hướng dẫn cấu hình server rồi kiểm tra lại, tránh mở rộng quản lý secret.

**Flow verify:** chạy workspace không có key → web báo chưa cấu hình → cấu hình key kiểm thử ở server, restart nếu cần → web báo đã cấu hình → kiểm tra response/job/log không chứa chuỗi key → lưu form thông thường.

**Đạt / chạy lại:** lưu form không thay key bằng dấu che hoặc rỗng; lỗi thiếu key chặn trước request dịch vụ; không trả secret qua API. Nếu bổ sung form ghi key sau này, phải là task riêng có nghiệm thu write-only.

### T27 — Tổng quan và lịch sử công việc thực tế

**Nhóm gốc:** V11-08/09. **Phụ thuộc:** T18, T22, T24.

**Output:** dashboard số truyện/chương/audio, job gần đây và liên kết cần xử lý; lịch sử/filter/phân trang job và report theo truyện.

**Flow verify:** hoàn thành một TTS, để một job lỗi, dừng một job → mở Tổng quan → bấm từng số/liên kết → đến đúng danh sách và phạm vi → reload/restart.

**Đạt / chạy lại:** số liệu từ DB/artifact hợp lệ; phân biệt trạng thái job với tình trạng audio; không cộng audio cũ/hỏng vào chỉ số “hiện hành” sai nghĩa. Thư viện rỗng không hiện dữ liệu minh họa.

### T28 — Chống job trùng và xung đột app/CLI

**Nhóm gốc:** V11-05/06/10. **Phụ thuộc:** T18, T20, T24.

**Output:** thống nhất khóa/ownership cho output và cache chung; cảnh báo conflict trên web/CLI. Bổ sung kiểm tra race cho cơ chế idempotency đã có từ T16.

**Flow verify:** hai tab cùng chạy một chương → một job hoặc conflict rõ; chạy CLI và web nhắm cùng output/cache → một bên chờ hoặc từ chối rõ → kết thúc rồi chạy lại → kiểm tra hash/trạng thái.

**Đạt / chạy lại:** không hai writer đồng thời; không coi hai truyện dùng tên chương giống nhau là cùng dữ liệu; khóa được giải phóng khi lỗi/crash. Không dùng việc vô hiệu hóa nút trên UI làm bảo vệ duy nhất.

### T29 — Kiểm chứng ranh giới truy cập và upload local

**Nhóm gốc:** V11-06/10. **Phụ thuộc:** T07, T13, T14, T26.

**Output:** bộ kiểm tra tích hợp và sửa các lỗ hổng phát hiện được cho Host/Origin, mutation từ ngoài app, upload, đường dẫn và secret. Bảo vệ cơ bản đã nằm trong các task trước, task này xác nhận đồng bộ.

**Flow verify:** truy cập app hợp lệ → upload/stream bình thường → gửi request Origin/Host lạ, path traversal, symlink, file quá giới hạn, artifact ID ngoài truyện → đối chiếu response/log và file trên đĩa.

**Đạt / chạy lại:** request không hợp lệ bị từ chối mà không đọc/ghi ngoài vùng; không có secret; app local và stream Range vẫn dùng được. Có lệnh chạy lại suite trên workspace kiểm thử.

### T30 — Backup/restore dữ liệu đang vận hành

**Nhóm gốc:** V11-02/10. **Phụ thuộc:** T20, T23, T24.

**Output:** quy trình/công cụ backup và restore DB + artifact + cấu hình không chứa secret; manifest/hash và xử lý job đang chạy. Có hướng dẫn chạy lại, chưa bắt buộc UI quản trị backup.

**Flow verify:** workspace có truyện, bản dịch, audio và job → đưa worker về điểm an toàn → backup → restore sang workspace mới → mở app → xem nội dung/nghe audio/tiếp tục job còn lại.

**Đạt / chạy lại:** kiểm chứng hash/quan hệ artifact; không lấy DB bằng copy thiếu nhất quán khi còn ghi; restore không ghi đè workspace thật. Phân biệt backup trước migration T04 với backup toàn kho vận hành ở task này.

### T31 — Cài provider và nghiệm thu giọng thật

**Nhóm gốc:** V11-01/10. **Phụ thuộc:** T03, T17, T25.

**Output:** hướng dẫn dependency tùy chọn cho provider được hỗ trợ; từ môi trường mới chạy doctor → thử giọng → TTS một chương ngắn bằng VieNeu thật. Provider khác ghi rõ đã/chưa thử trên môi trường hiện tại.

**Flow verify:** cài theo tài liệu → doctor → thử giọng → tạo chương VI ngắn → nghe và ffprobe → chạy lại xác nhận cache; thử provider thiếu dependency để thấy hướng khắc phục.

**Đạt / chạy lại:** ghi cấu hình, thời gian và kết quả; không tuyên bố mọi provider đã đạt khi chỉ thử VieNeu. Không tự dùng dịch vụ tính phí; phần đó nghiệm thu riêng theo cấu hình được người dùng chọn.

### T32 — Trạng thái UI, bàn phím và bố cục màn hình nhỏ

**Nhóm gốc:** V11-07/08/09/10. **Phụ thuộc:** T10, T14, T19, T22, T24, T27.

**Output:** hoàn thiện loading/rỗng/lỗi/success cho flow đã có; focus dialog, Escape, validation, action không phụ thuộc hover; desktop và màn hình hẹp theo mock.

**Flow verify:** dùng bàn phím tạo truyện → import → tạo job → đóng dialog → làm API mất kết nối rồi phục hồi → mở thư viện rỗng → thử viewport hẹp và bảng cuộn ngang.

**Đạt / chạy lại:** không mất lựa chọn ngoài ý muốn, không clipping action chính, error có đường tiếp tục; không nhảy focus khi polling. Có ảnh của trạng thái quan trọng và luồng thao tác cụ thể.

### T33 — Khởi động thống nhất, cài mới và giữ CLI tương thích

**Nhóm gốc:** V11-01/07/10. **Phụ thuộc:** T20, T28, T29, T30, T31, T32.

**Output:** quy trình khởi động/dừng app/API/worker, health thành phần, hướng dẫn cài mới/nâng cấp và CLI dùng chung lõi. Tách chế độ production local với workspace kiểm thử; phiên bản thực thi vẫn chỉ đổi khi phát hành.

**Flow verify:** checkout sạch → cài theo hướng dẫn → khởi động bằng quy trình thống nhất → import/TTS trên web → dừng → restart → chạy lại các CLI v1.0 chính trong workspace riêng.

**Đạt / chạy lại:** không cần chạy tay nhiều terminal cho thao tác thường ngày; lỗi startup/cổng bận/worker chết được báo; không mồ côi worker sau shutdown. CLI giữ hành vi và checkpoint hoặc có migration tương thích được tài liệu hóa.

### T34 — Nghiệm thu release và bộ tài liệu sử dụng

**Nhóm gốc:** V11-10. **Phụ thuộc:** T01–T33.

**Output:** báo cáo nghiệm thu toàn v1.1, hướng dẫn sử dụng với ảnh từ app thật, release notes và danh sách hạn chế; đối chiếu đủ 10 kịch bản trong requirements. Đây là task nghiệm thu tích hợp, không phải nơi dồn chức năng chưa làm.

**Flow verify:** trên workspace mới chạy từ tạo truyện → import TXT/MP3 → cấu hình → TTS → dừng/tiếp tục → dịch/process → ghép → nghe/tải → restart → backup/restore. Chạy lại trên dữ liệu đã có và kiểm tra tái sử dụng/chống trùng.

**Đạt / chạy lại:** có một lần VieNeu thật; thử dịch API thật trên mẫu ngắn khi có cấu hình và chấp thuận sử dụng dịch vụ. Nếu thiếu điều kiện ngoài hệ thống, ghi rõ mục chưa nghiệm thu và chưa kết luận release hoàn thành. Không cần triển khai lại tính năng ở task này; lỗi tìm thấy quay về task liên quan.

## 5. Phụ thuộc và thứ tự thực hiện

Thứ tự đề xuất để hạn chế chờ và có demo sớm:

```text
T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10
→ T11 → T12 → T13 → T14 → T26 → T15 → T16 → T17 → T18 → T19
→ T20 → T21 → T22 → T23 → T24 → T25 → T27 → T28
→ T29 → T30 → T31 → T32 → T33 → T34
```

Thứ tự trên là một cách triển khai hợp lệ, không thêm phụ thuộc giả. Có thể làm T11/T15 sau T05; T26 ngay sau T11; T24 sau T18; T31 sau T25; kiểm tra phụ thuộc trên từng task trước khi bắt đầu. T04 là task nền duy nhất trong đợt B cần công cụ kiểm chứng riêng; các task chức năng còn lại ưu tiên giao trọn flow qua web.

## 6. Ánh xạ với 10 nhóm trong roadmap

| Nhóm gốc | Task thực thi |
|---|---|
| V11-01 — Môi trường/provider | T03, T25, T31, T33 |
| V11-02 — Dữ liệu/migration | T04, T05, T30 |
| V11-03 — Cấu hình/contract | T01, T11, T12, T16, T26 |
| V11-04 — Import | T06, T07, T08, T13 |
| V11-05 — Job/worker | T15–T24, T28 |
| V11-06 — API/media/local | Được giao cùng từng feature; trọng tâm T01, T10, T14, T26, T29 |
| V11-07 — App shell | T01, T32, T33 |
| V11-08 — UI dữ liệu/cấu hình | T05–T13, T25–T27, T32 |
| V11-09 — UI job/audio | T14–T25, T27, T32 |
| V11-10 — Kiểm chứng/bàn giao | T02, T21, T28–T34 và evidence từng task |

API validation, cách ly dữ liệu, trạng thái lỗi và tài liệu chạy thử thuộc chính task tạo ra feature; các task cuối kiểm chứng xuyên suốt và hoàn thiện, không thay thế trách nhiệm đó.

## 7. Cách dùng backlog

- Khi triển khai một task, chỉ cần tham chiếu ID: ví dụ “Triển khai T06 và bàn giao flow nghiệm thu”.
- Trước khi làm, kiểm tra task phụ thuộc thực sự đã đạt; không dùng mock làm bằng chứng feature đã có.
- Chưa đạt khi còn phải sửa DB/file bằng tay để demo hoặc chạy lại.
- Không tự chuyển trạng thái task sang hoàn thành vì đã có code, ảnh mock hoặc test giả lập ở phần cần nghiệm thu thật.
- Đã tạo 34 issue trên Linear theo yêu cầu người dùng, cùng một milestone **v1.1**; khi khởi tạo đều ở Backlog và chưa triển khai. Xem [bảng ánh xạ](../../linear-reference.md). Không tự tạo thêm issue trùng, chat hoặc lịch làm việc từ backlog.
