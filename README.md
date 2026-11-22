# Furina Chat

Ứng dụng chat trong mạng LAN (LAN chat) viết bằng Python, giao diện desktop dựa trên **CustomTkinter**. Giao diện hiện tại lấy cảm hứng từ các ứng dụng nhắn tin hiện đại: sidebar danh sách hội thoại bên trái, khung chat bên phải, bảng chọn sticker và các tầng mạng TCP/UDP tách riêng.

> **Lưu ý quan trọng:** Repository này đang trong giai đoạn dựng khung. Vui lòng **không sửa bất kỳ dòng code nào** khi chỉ cần đọc/tham khảo tài liệu. Mọi thay đổi về mã nguồn cần được thống nhất trước.

## Tính năng

### Đã có trong giao diện

- Cửa sổ chính 950x650 với theme sáng, màu chủ đạo `#6A49FA` / `#453284`.
- Sidebar hiển thị tiêu đề "Chats", ô tìm kiếm và nút "Đổi trạng thái".
- Khung chat có vùng hiển thị tin nhắn (chỉ đọc), ô nhập tin nhắn và nút "Gửi".
- Gửi tin nhắn cục bộ: tin nhắn được chèn vào khung chat và ô nhập được xóa trắng.
- Luồng giả lập sự kiện mạng: sau 2 giây, một tin nhắn mẫu được đẩy vào khung chat bằng `threading` (chạy nền, không chặn GUI).

### Đang ở dạng khung (chưa triển khai)

Các module dưới đây đã được tạo file nhưng chưa có nội dung, dành cho các bước tiếp theo:

- `core/` — điều phối ứng dụng, event bus, quản lý trạng thái.
- `network/` — giao thức, dịch vụ TCP, UDP và truyền file.
- `ui/sticker_picker.py` — bảng chọn sticker.
- `main.py`, `config.py` — điểm khởi chạy và cấu hình.

## Công nghệ sử dụng

| Thành phần | Công nghệ |
| --- | --- |
| Ngôn ngữ | Python 3.9+ |
| Giao diện | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (dựa trên Tkinter) |
| Đa luồng | `threading` (luồng daemon cho sự kiện nền) |
| Mạng (dự kiến) | TCP, UDP, truyền file qua socket |

## Cấu trúc dự án

```text
furina-chat/
├── main.py                  # Điểm khởi chạy (chưa triển khai)
├── config.py                # Cấu hình ứng dụng (chưa triển khai)
├── core/
│   ├── controller.py        # Điều phối logic ứng dụng (chưa triển khai)
│   ├── event_bus.py         # Phát/nhận sự kiện nội bộ (chưa triển khai)
│   └── state.py             # Quản lý trạng thái (chưa triển khai)
├── network/
│   ├── protocol.py          # Định nghĩa giao thức tin nhắn (chưa triển khai)
│   ├── tcp_service.py       # Kết nối TCP (chưa triển khai)
│   ├── udp_service.py       # Gói tin UDP (chưa triển khai)
│   └── file_service.py      # Truyền/nhận file (chưa triển khai)
└── ui/
    ├── main_window.py       # Cửa sổ chính, khởi tạo sidebar và khung chat
    ├── chat_panel.py        # Khung hiển thị và gửi tin nhắn
    ├── peer_sidebar.py      # Sidebar danh sách hội thoại
    └── sticker_picker.py    # Bảng chọn sticker (chưa triển khai)
```

## Yêu cầu hệ thống

- Python 3.9 trở lên (khuyến nghị 3.10+).
- Tkinter có sẵn trong bản cài Python chính thức trên Windows.
- CustomTkinter.

## Cài đặt

```bash
# 1. Tạo và kích hoạt môi trường ảo (khuyến nghị)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Cài phụ thuộc
pip install customtkinter
```

## Chạy ứng dụng

Do `main.py` chưa có nội dung, chạy tạm giao diện qua module `ui.main_window` từ thư mục gốc của dự án:

```bash
python -m ui.main_window
```

Hoặc thêm đoạn khởi chạy tối thiểu vào `main.py` khi được phép chỉnh sửa mã nguồn:

```python
from ui.main_window import MainWindow

if __name__ == "__main__":
    MainWindow().mainloop()
```

Sau đó chạy:

```bash
python main.py
```

## Trạng thái hiện tại

| Hạng mục | Trạng thái |
| --- | --- |
| Giao diện cơ bản (sidebar + chat) | Hoạt động |
| Gửi tin nhắn cục bộ | Hoạt động |
| Giả lập tin nhắn đến từ mạng | Hoạt động (dữ liệu giả lập) |
| Kết nối TCP/UDP thật | Chưa triển khai |
| Phát hiện peer trong LAN | Chưa triển khai |
| Truyền file | Chưa triển khai |
| Sticker | Chưa triển khai |

## Định hướng phát triển

1. Hoàn thiện `core/event_bus.py` và `core/state.py` để tách sự kiện mạng khỏi lớp giao diện.
2. Cài đặt `network/protocol.py` (định dạng tin nhắn, mã hóa/giải mã).
3. Thêm `network/tcp_service.py` cho kết nối 1-1 và `network/udp_service.py` cho quảng bá/phát hiện peer.
4. Đổ dữ liệu peer thật vào `PeerSidebar` và tin nhắn thật vào `ChatPanel` thông qua controller.
5. Bổ sung `file_service.py` và `sticker_picker.py` sau khi luồng chat ổn định.

## Ghi chú phát triển

- Giao diện chạy trên luồng chính của Tkinter; các tác vụ chờ/IO nên đặt trong luồng riêng (tham khảo `simulate_network_event` trong `ui/main_window.py`).
- Khi cập nhật nội dung `CTkTextbox`, cần chuyển `state` sang `normal`, chèn dữ liệu, rồi trả về `disabled` để giữ khung chat chỉ đọc.
- Không commit thư mục `__pycache__/` hay file `*.pyc` (đã có trong `.gitignore`).
