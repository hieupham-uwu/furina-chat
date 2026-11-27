# Furina Chat

Furina Chat là ứng dụng desktop để nhắn tin và chia sẻ tệp giữa các máy trong cùng mạng LAN. Mỗi máy chạy cùng một chương trình và kết nối trực tiếp với các máy khác. Ứng dụng dùng UDP để tìm người và cập nhật trạng thái, dùng TCP để nhắn tin và truyền tệp.

## Cài đặt

Cần Python **3.10 trở lên**, Tkinter và kết nối LAN IPv4 để thử giữa các máy. Trên Windows, bản Python từ python.org có sẵn tùy chọn cài Tcl/Tk. Nếu cần kiểm tra Tkinter, chạy `python -m tkinter`.

Mở PowerShell tại thư mục chứa `main.py` rồi chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Trên macOS hoặc Linux, dùng `python3 -m venv .venv` và thay `.\.venv\Scripts\python.exe` bằng `./.venv/bin/python` trong các lệnh bên dưới. Nếu hệ điều hành đóng gói Tkinter riêng, cài gói Tkinter cho bản Python đang dùng.

## Khởi chạy trên LAN

Trên mỗi máy cùng mạng Wi-Fi hoặc Ethernet, mở PowerShell ở thư mục dự án và chạy lệnh sau. Dùng tên khác nhau để dễ nhận diện.

```powershell
.\.venv\Scripts\python.exe main.py --name "Máy A"
```

| Tùy chọn | Công dụng |
| --- | --- |
| `--name "Máy A"` | Đặt tên hiển thị. Nếu bỏ qua, app dùng `FURINA_NAME`, tên tài khoản hoặc tên máy. |
| `--port 5001` | Chọn cổng TCP lắng nghe. Mặc định hệ điều hành cấp cổng trống và app quảng bá cổng đó trong `HELLO`. |
| `--discovery-ip 192.168.1.255` | Chọn địa chỉ đích gửi discovery. Ví dụ này dùng broadcast của mạng `192.168.1.0/24`. Dùng địa chỉ broadcast tương ứng với mạng thực tế của nhóm. |

## Sử dụng

- **Đang online** liệt kê người đang được phát hiện qua UDP, gồm cả người đặt trạng thái **Away**. Chọn một người để mở chat và xem IP, cổng TCP ở đầu khung chat.
- **Lịch sử** liệt kê các cuộc trò chuyện đã có tin hoặc tệp trong phiên đang chạy. Bạn vẫn xem được nội dung khi người kia Offline. Lịch sử và bản nháp được giữ trong bộ nhớ xuyên suốt phiên sử dụng.
- Nút trạng thái chuyển giữa **Online** và **Away**. Khi một người xuất hiện hoặc mất tín hiệu UDP, mục **Chats** hiện thông báo. Sau khoảng 10 giây thiếu `HELLO`, người đó được đánh dấu **Offline**.
- Nhấn **Enter** hoặc nút **Gửi** để gửi tin, tối đa **4.000 ký tự** mỗi tin. Tin từ cuộc chat khác được lưu và có số chưa đọc cạnh tên người gửi.
- Dùng các nút tệp, ảnh và sticker cạnh ô nhập. Từng tệp có thanh phần trăm riêng. Nút hủy xuất hiện khi lượt gửi còn có thể dừng. Tệp nhận nằm trong **`downloads/`** cạnh `main.py`.
- **Rời chat** đóng phiên TCP với người đang chọn bằng `BYE` và giữ nội dung cũ, bản nháp.
- **Thoát app** ở cuối thanh bên đóng toàn bộ ứng dụng, giống nút **X**. App dừng `HELLO` và gửi `BYE` cho các kết nối chat còn mở nếu đường truyền vẫn hoạt động.

## Kiểm thử

Chạy bộ kiểm thử tự động từ thư mục dự án:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bộ kiểm thử dùng kết nối cục bộ để kiểm tra discovery, khung giao thức TCP, tin nhắn Unicode, kết nối đồng thời, `BYE`, truyền file, hủy gửi và dọn tệp nhận dở.

Kiểm tra giao diện trên hai hoặc ba máy cùng LAN:

1. Mở app trên mỗi máy với tên khác nhau. Kiểm tra mọi máy thấy nhau ở **Đang online**. Đổi Online/Away ở một máy rồi quan sát phía còn lại.
2. Nhắn qua lại, sau đó để A chat với B và cho C gửi hai tin tới A. Kiểm tra A giữ nguyên ô đang gõ, thấy số chưa đọc của C và đọc được cả hai tin khi chuyển sang C.
3. Gửi file đủ lớn để quan sát phần trăm. Vừa gửi vừa nhắn tin, thử hủy một lượt khác và kiểm tra tệp đã nhận trong `downloads/`.
4. Nhấn **Rời chat** ở A. Kiểm tra B nhận thông báo rời chat, hai máy vẫn hiện trong **Đang online** và có thể mở lại tin cũ trong **Lịch sử**.
5. Nhấn **Thoát app** ở B. Trên A, đợi khoảng 10 giây để thấy thông báo Offline và B rời tab **Đang online**. Mở lại **Lịch sử** để kiểm tra nội dung cũ còn đọc được.

Nếu hai máy chưa thấy nhau, kiểm tra chúng có ở cùng mạng IPv4, Wi-Fi có chặn máy khách giao tiếp với nhau và tường lửa có cho Python nhận UDP **9999** và kết nối TCP đến trên mạng riêng. Với máy có nhiều adapter, có thể dùng `--discovery-ip` để chọn đích broadcast của LAN cần thử.

## Kiến trúc

| Thành phần | Vai trò |
| --- | --- |
| `main.py`, `config.py` | Khởi tạo GUI, dịch vụ mạng và cấu hình chung. |
| `ui/` | Giao diện CustomTkinter gồm danh sách peer, khung chat và bảng sticker. GUI cập nhật trên luồng chính. |
| `core/` | Controller điều phối thao tác, EventBus chuyển sự kiện từ luồng nền về GUI, AppState giữ lịch sử, trạng thái và số chưa đọc. |
| `network/udp_service.py` | Quảng bá `HELLO` trên UDP 9999 mỗi 3 giây. Lắng nghe và loại peer hết hạn khỏi danh sách khám phá. |
| `network/tcp_service.py` | Chấp nhận kết nối TCP, trao đổi `HI` để nhận diện peer và phân biệt kết nối chat với kết nối truyền tệp. |
| `network/file_service.py` | Mỗi lượt truyền có kết nối TCP và luồng riêng. Máy nhận ghi tệp tạm, chuyển thành tệp đích khi nhận đủ và gửi `FILE_OK`. Nếu lượt nhận lỗi, app dọn tệp tạm. |
| `network/protocol.py` | Mã hóa và đọc gói JSON UTF-8. Frame TCP gồm magic `Furina`, 4 byte độ dài header theo thứ tự mạng, header JSON và dữ liệu file/ảnh nếu có. |
| `tests/` | Bộ kiểm thử protocol, discovery, chat và truyền file. |
