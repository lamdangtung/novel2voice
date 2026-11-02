# novel2voice v1.1 — UI/UX reference

Ngày lưu: **28/10/2026**. Người dùng đã đồng ý với hướng UI/UX trong mock này và yêu cầu lưu để tham khảo/viết tài liệu. Đây là baseline thiết kế; không phải xác nhận rằng các chức năng v1.1 đã triển khai hoặc nghiệm thu.

## Mở và sử dụng

Mở [index.html](index.html) bằng trình duyệt hiện đại. Không cần chạy app, API, Python, model hoặc cung cấp API key. Trang hoạt động với dữ liệu mẫu; icon và thành phần hỗ trợ có thể cần Internet vì bản xuất có tài nguyên CDN. Nếu offline, phần tương tác chính vẫn dùng mã nhúng nhưng icon có thể không hiện.

Các lựa chọn điều hướng có thể được nhớ cục bộ bởi bản xuất. Dữ liệu truyện, import, cấu hình và queue là dữ liệu mô phỏng trong bộ nhớ; reload có thể đưa chúng về dữ liệu mẫu ban đầu. Không dùng bản này để lưu nội dung thật hoặc nhập secret.

## Tệp tham chiếu

| Tệp | Vai trò |
|---|---|
| [index.html](index.html) | Bản xuất mở độc lập để review UI/UX |
| [novel2voice-studio.fragment.html](novel2voice-studio.fragment.html) | Bản nguồn mock đã được review trong cuộc trò chuyện, giữ nguyên khi lưu |
| `screenshots/` | Ảnh các màn hình/luồng tiêu biểu của bản xuất, phục vụ viết docs |
| [Yêu cầu v1.1](../../v1.1-requirements.md) | Nguồn yêu cầu chức năng và điều kiện nghiệm thu chính thức |
| [Roadmap](../../../roadmap.md) | Kế hoạch các phiên bản và phụ thuộc |

Bản xuất chứa bản sao nội dung nguồn nên việc sửa fragment không tự cập nhật index.html. Khi thay đổi thiết kế, xuất lại, kiểm tra tương tác và cập nhật ảnh/ghi chú cùng nhau. Giữ mốc hiện tại để so sánh; hướng mới nên được lưu ở một revision riêng.

## Hướng thiết kế đã thống nhất

- Giao diện tiếng Việt, dành cho thao tác trên máy local, desktop là màn hình chính.
- Sidebar: Tổng quan, Thư viện truyện, Công việc, Cấu hình, Môi trường.
- Màn hình trọng tâm là chi tiết bộ truyện: thống kê, danh sách chương, trạng thái audio và action theo lựa chọn.
- Dùng bảng để quản lý nhiều chương; tìm theo số/tên và lọc theo trạng thái.
- Các action nhiều bước đi qua dialog có thiết lập/xem trước trước khi bắt đầu.
- Nghe audio đặt gần danh sách chương; xem nội dung và lỗi qua chi tiết chương.
- Tách cấu hình workspace và cấu hình truyện trong điều hướng.
- Có bố cục thích ứng màn hình hẹp; bảng nhiều cột có thể cuộn ngang.
- Phong cách: nền trung tính, vùng nội dung sáng/tối theo hệ thống, màu tím xanh cho action chính; trạng thái luôn có nhãn chữ.

## Màn hình và luồng review

| Màn hình / luồng | Cách mở | Điểm cần tham khảo |
|---|---|---|
| Chi tiết truyện | Mặc định, hoặc Thư viện → Mở truyện | Thống kê, tab, bảng chương, chọn nhiều, player |
| Tổng quan | Sidebar → Tổng quan | Công việc gần đây và tiếp tục làm việc |
| Thư viện | Sidebar → Thư viện truyện | Thẻ truyện, tiến độ, tạo truyện mẫu |
| Chi tiết chương | Bấm tên chương / Chi tiết / Xem lỗi | Nội dung, trạng thái, provenance và thử lại |
| Import | Trong truyện → Import → Chọn dữ liệu mẫu | Preview, chương trùng, ánh xạ MP3, xác nhận |
| Tạo tác vụ | Tạo tác vụ hoặc chọn chương → Tạo audio | Chọn dịch/TTS/process/ghép, phạm vi, preview, queue |
| Công việc | Sidebar hoặc Xem tác vụ | Tiến độ, checkpoint, dừng/tiếp tục, lỗi và retry |
| Cấu hình | Sidebar hoặc tab Cấu hình truyện | Provider, giọng, batch, retry, glossary và trạng thái key |
| Môi trường | Sidebar → Môi trường | Kiểm tra dependency; phân biệt doctor và thử giọng |

### Kịch bản walkthrough ngắn

1. Mở truyện mẫu; tìm chương, đổi bộ lọc và chọn nhiều chương.
2. Mở chi tiết chương lỗi và chương có MP3 nhập từ trước.
3. Import dữ liệu mẫu; xem các ánh xạ và chương trùng trước khi xác nhận.
4. Tạo tác vụ; chọn action/phạm vi, xem trước và bắt đầu mô phỏng.
5. Mở Công việc; dừng, tiếp tục hoặc mô phỏng hoàn tất.
6. Đổi provider/giọng trong Cấu hình; thử dialog thử giọng.
7. Mở Môi trường rồi quay lại Thư viện, tạo truyện mẫu để xem trạng thái rỗng.

## Giới hạn cần giữ rõ khi viết docs

- Không gọi API, không tạo/dịch/ghép audio, không đọc hay ghi kho truyện thật.
- Play/tua và tiến độ chỉ minh họa giao diện, không có giọng đọc thật.
- Số liệu, giọng, tình trạng key và dependency là mẫu, không phải kiểm tra máy hiện tại.
- Các form và checkbox chưa mô phỏng đầy đủ mọi quy tắc nghiệp vụ. Một số kết quả preview được đặt sẵn.
- Quản lý cấu hình riêng, queue theo từng truyện, phần trăm, số chương và dữ liệu sau chuyển màn hình chưa phải mô hình dữ liệu chuẩn.
- Chưa bao phủ đầy đủ upload thật, API validation, loading, tất cả ca lỗi, phân trang, phục hồi restart, quản lý secret, tải file hay accessibility.
- Mock không thay thế API contract, yêu cầu bảo toàn dữ liệu và kịch bản nghiệm thu trong requirements.

Khi viết tài liệu sản phẩm thật, thay ảnh/số liệu mô phỏng bằng kết quả đã triển khai và xác minh. Khi mock khác yêu cầu chức năng, dùng requirements làm chuẩn và cập nhật thiết kế trước khi nghiệm thu.

## Ảnh tham chiếu

Ảnh chụp từ bản xuất, giao diện sáng; các ảnh luồng sau import có thể có dữ liệu mẫu khác màn hình mặc định. Ảnh mobile thể hiện viewport, bảng có thể cuộn ngang.

- [Chi tiết truyện — desktop](screenshots/01-story-desktop.png)
- [Import — kiểm tra ánh xạ](screenshots/02-import-preview.png)
- [Tác vụ — xem trước](screenshots/03-job-preview.png)
- [Danh sách công việc](screenshots/04-jobs.png)
- [Cấu hình](screenshots/05-settings.png)
- [Thư viện truyện](screenshots/06-library.png)
- [Môi trường](screenshots/07-environment.png)
- [Chi tiết truyện — mobile](screenshots/08-story-mobile.png)

Bản xuất đã được kiểm tra mở độc lập và thử luồng import → chọn chương → tạo job → dừng/tiếp tục → điều hướng, không ghi nhận lỗi JavaScript trong lần kiểm tra ngày 28/10/2026.
