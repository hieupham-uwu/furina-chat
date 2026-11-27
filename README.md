# Furina Chat

Ứng dụng chat trong mạng LAN (LAN chat) viết bằng Python, giao diện desktop dựa trên **CustomTkinter**. Giao diện hiện tại lấy cảm hứng từ các ứng dụng nhắn tin hiện đại: sidebar danh sách hội thoại bên trái, khung chat bên phải, bảng chọn sticker và các tầng mạng TCP/UDP tách riêng.

## Tính năng

- Tự tìm các máy chạy Furina Chat trong LAN bằng UDP.
- Chat riêng với từng người và gửi sticker, ảnh, tệp qua TCP.
- Tìm người chat trong danh sách **Chats**, xem tin chưa đọc và đổi trạng thái online/away.

## Công nghệ sử dụng

| Thành phần | Công nghệ |
| --- | --- |
| Ngôn ngữ | Python 3.10+ |
| Giao diện | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (dựa trên Tkinter) |
| Đa luồng | `threading` (luồng daemon cho sự kiện nền) |
| Mạng | TCP, UDP, truyền file qua socket |

## Cấu trúc dự án

```text
furina-chat/
├── main.py                  # Điểm khởi chạy
├── config.py                # Cấu hình ứng dụng
├── core/
│   ├── controller.py        # Điều phối logic ứng dụng
│   ├── event_bus.py         # Phát/nhận sự kiện nội bộ
│   └── state.py             # Quản lý trạng thái
├── network/
│   ├── protocol.py          # Định nghĩa giao thức tin nhắn
│   ├── tcp_service.py       # Kết nối TCP
│   ├── udp_service.py       # Gói tin UDP
│   └── file_service.py      # Truyền/nhận file
└── ui/
    ├── main_window.py       # Cửa sổ chính, khởi tạo sidebar và khung chat
    ├── chat_panel.py        # Khung hiển thị và gửi tin nhắn
    ├── peer_sidebar.py      # Sidebar danh sách hội thoại
    └── sticker_picker.py    # Bảng chọn sticker
```

## Cài đặt

Dùng Python 3.10 trở lên có Tkinter. Trong thư mục repo trên mỗi máy, chạy:

```powershell
python -m pip install -r requirements.txt
```

## Chat giữa hai máy

Kết nối hai máy vào cùng mạng LAN hoặc Wi-Fi. Chạy lệnh tương ứng trên từng máy:

```powershell
# Máy 1
python main.py --gui --name May1

# Máy 2
python main.py --gui --name May2
```

Đợi vài giây để tên máy kia xuất hiện trong danh sách **Chats**, rồi bấm vào tên để gửi tin. Ảnh và tệp nhận được nằm trong thư mục `downloads/`.

Nếu máy kia không xuất hiện, kiểm tra xem mạng Wi-Fi có cho phép các thiết bị liên lạc với nhau và tường lửa có cho phép Python trên mạng riêng hay không. UDP discovery dùng cổng `9999`. Có thể chạy với `--tcp-port 5000` nếu cần dùng một cổng TCP cố định.

Khi máy có nhiều card mạng, thêm `--discovery-ip` cùng địa chỉ IPv4 Wi-Fi của máy kia để gửi gói tìm máy trực tiếp. Ví dụ, nếu máy kia có IP `192.168.1.20`:

```powershell
python main.py --gui --name May1 --discovery-ip 192.168.1.20
```

Khi máy kia chọn cuộc chat hoặc gửi tin, kết nối TCP đến sẽ thêm tên máy đó vào **Chats**.

## Kiểm thử

- `python main.py --name May1` chạy bản console để kiểm tra UDP và TCP.
- `python test_ui.py` chạy giao diện với dữ liệu demo.
- `python -m unittest discover -s tests` chạy bộ kiểm thử tự động.

## Ghi chú phát triển

Giao diện chạy trên luồng chính của Tkinter. Các dịch vụ mạng chạy nền và chuyển sự kiện sang giao diện qua `EventBus`. Xem thêm [tài liệu kiến trúc](docs/architecture.md).
