# Bug report – Furina Chat

- Ngày kiểm tra: 2026-11-27
- Phạm vi: lớp UI/controller (phần mạng UDP/TCP/truyền file đã chạy ổn trước đó)
- Môi trường: Windows, Python 3.12, `.venv`, CustomTkinter 6.0.0, Pillow 13.0.0

## Tóm tắt

Đã sửa 8 lỗi. Trong đó 3 lỗi chặn hoàn toàn giao diện (không chọn được peer, không cập nhật trạng thái), 5 lỗi còn lại là lỗi chức năng/độ bền.

| # | Lỗi | Mức độ | Trạng thái |
|---|-----|--------|------------|
| 1 | `MainWindow.state` che mất `Tk.state()` | Chặn UI | Đã sửa |
| 2 | `select_peer` gọi `set_header(..., status=...)` sai chữ ký | Chặn UI | Đã sửa |
| 3 | Cập nhật Tk từ thread nền | Chặn UI (demo, timeout) | Đã sửa |
| 4 | `open_chat` chạy đồng bộ trên luồng UI | Treo UI tới 5 giây | Đã sửa |
| 5 | Bỏ qua `chat_connected` / `chat_disconnected` | Mất thông tin | Đã sửa |
| 6 | Một event lỗi làm chết vòng poll 100 ms | Độ bền | Đã sửa |
| 7 | `shutdown` dừng TCP trước file_service | Đóng file dở | Đã sửa |
| 8 | `requirements.txt` rỗng dù UI cần thư viện | Cài đặt | Đã sửa |

## Chi tiết

### 1. `MainWindow.state` che mất `Tk.state()`

**Hiện tượng:** tạo cửa sổ xong thì mọi thao tác controller đổ dây chuyền:

```
TypeError: 'AppState' object is not callable
AttributeError: 'function' object has no attribute 'lock'
```

**Nguyên nhân:** `ui/main_window.py` gán `self.state = ...`. `Tk` đã có phương thức `state()`; CustomTkinter gọi `window.state()` trong scaling tracker nên nhận `AppState` thay vì hàm. Đồng thời `refresh_sidebar` đọc `self.state.lock`, nhưng khi `self.state` bị thay bằng bound method thì lại không có `.lock`.

**Cách sửa:** đổi thuộc tính sang `self.app_state`, import singleton với bí danh `app_state_singleton` để bỏ hẳn `globals()["state"]`.

- `ui/main_window.py:46`: `self.app_state = state or app_state_singleton`
- Toàn bộ `refresh_sidebar`, `_seed_demo_data`, `_on_close` dùng `self.app_state`.

### 2. Sai chữ ký `set_header`

**Hiện tượng:** chọn peer là `TypeError: ChatPanel.set_header() got an unexpected keyword argument 'status'`.

**Nguyên nhân:** `core/controller.py` gọi `set_header(text, status=...)`, còn `ui/chat_panel.py` khai báo `_status`.

**Cách sửa:** nhận cả hai tên để không vỡ lời gọi cũ.

- `ui/chat_panel.py:193`: `def set_header(self, _text="", status="", _status="")`

### 3. Cập nhật Tk từ thread nền

**Hiện tượng:**

- Chế độ demo: nhãn trạng thái kẹt ở "Đang gửi...", thanh tiến độ rỗng, thread gửi chết giữa chừng.
- Chạy mạng thật: sau 5 giây không bao giờ hiện "Chưa gửi được" ở `_schedule_unsent_timeout`.
- Log: `RuntimeError: main thread is not in main loop`.

**Nguyên nhân:** `safe_update_status` / `safe_progress` gọi `self.winfo_exists()` và `self.after()` ngay trên thread worker. `_demo_incoming_loop` cũng gọi `self.after(0, _push)` từ thread. Đã kiểm chứng riêng: `after()` từ thread khác ném `RuntimeError`.

**Cách sửa:** thread nền chỉ đẩy callback vào `queue.Queue`; luồng chính (vòng poll 100 ms) lấy ra thực thi.

- `ui/main_window.py:95` `_post_ui`, `:101` `_drain_ui_queue`
- `safe_update_status` (`:112`) và `safe_progress` (`:123`) chỉ enqueue
- `_poll_event_bus` (`:134`) gọi `_drain_ui_queue()` mỗi nhịp
- `_demo_incoming_loop` dùng `self._post_ui(_push)` (`:249`)

### 4. `open_chat` chặn luồng UI

**Hiện tượng:** chọn peer đang offline/không tới được thì cửa sổ đứng tới 5 giây (`HI_FRAME_TIMEOUT`).

**Cách sửa:**

- `core/controller.py:68` `_open_chat_async` chạy trong thread nền khi `select_peer`.
- Thêm `core/controller.py:96` `_deliver`: nếu chat chưa sẵn sàng thì chờ/mở trong thread nền tối đa `CHAT_READY_TIMEOUT = 4.0` giây (`:13`), hết hạn thì để bộ hẹn giờ hiển thị "Chưa gửi được".
- `network/tcp_service.py:322` thêm `has_chat(peer_id)` để controller kiểm tra kết nối.

### 5. Bỏ qua `chat_connected` / `chat_disconnected`

**Hiện tượng:** peer rớt kết nối chat nhưng giao diện không báo gì; không có phản hồi khi kết nối lại.

**Cách sửa:** thêm nhánh xử lý trong `process_event`:

- `chat_connected` (`core/controller.py:358`): đánh dấu peer `online`, refresh sidebar.
- `chat_disconnected` (`:367`): nếu là peer đang mở thì hiện banner "Mất kết nối chat với X (lý do). Gửi tin mới để kết nối lại." Việc gửi tin tiếp theo sẽ tự mở lại kết nối nhờ `_deliver`.

### 6. Vòng poll chết khi một event lỗi

**Hiện tượng:** chỉ cần một handler ném exception là `self.after(100, ...)` cuối hàm không được gọi, toàn bộ event sau đó không bao giờ được xử lý.

**Cách sửa:** bọc `controller.process_event(event)` trong `try/except` tại `ui/main_window.py:134`. Callback UI trong hàng đợi cũng được bọc riêng.

### 7. Thứ tự `shutdown`

**Cách sửa:** `core/controller.py:544` dừng theo thứ tự `file_service → tcp_service → udp_service` để phiên truyền đang dở được đóng gọn trước khi TCP tắt.

### 8. `requirements.txt` rỗng

**Cách sửa:** thêm `customtkinter>=5.2` và `pillow>=10.0`. Trước đó UI chỉ chạy được vì Pillow được cài tay vào `.venv`.

## Kiểm chứng sau khi sửa

| Bài kiểm tra | Kết quả |
|---|---|
| `python -m compileall config.py core network ui main.py test_ui.py tests` | OK |
| `python -m unittest discover -s tests` | 21/21 PASS |
| UDP thật: discovery 2 chiều, `away` lan truyền, hết hạn sau 10 giây | 4/4 PASS |
| TCP chịu rác: `"abc"`, header quá lớn, client treo 6 giây | 3/3 PASS (chat mới vẫn mở và nhận tin) |
| UI smoke (không còn workaround): `state()` của Tk, sticker 15 ảnh, nháp, gửi text/sticker/ảnh, trạng thái demo lên "Đã nhận", progress 75%, banner mất kết nối, unread | 11/11 PASS |
| Controller + TCP thật: `select_peer` trả về 0.000s, chat mở nền, text/sticker tới peer, `message_sent` cập nhật UI, banner khi rớt, thứ tự shutdown | 7/7 PASS |
| Timer 5 giây không có đích gửi | PASS, UI hiện "Chưa gửi được" |

Lệnh chạy lại:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe test_ui.py
```

## Chưa sửa (việc tiếp theo, không phải lỗi chặn)

- Chưa có entry production nối `EventBus` + `UDPService` + `TCPService` + `file_service` vào `MainWindow`; `enable_local_preview=True` vẫn là mặc định nên bản chạy chỉ có dữ liệu giả.
- `core/models.py` chưa có; `core/state.py` còn hardcode `my_name`, `my_tcp_port`.
- Tên hằng giữa `config.py` và UI còn lệch (`MAX_MSG_CHARS`, `DOWNLOADS_DIR`, `STICKERS_DIR`...); UI đang dùng giá trị fallback.
- `README.md` và `docs/architecture.md` chưa cập nhật trạng thái sau khi sửa.
- Gửi nhiều tin liên tiếp trong lúc chat đang mở nền: mỗi tin chờ trong một thread riêng nên thứ tự không được bảo đảm tuyệt đối. Trường hợp bình thường (chat đã mở) vẫn gửi tuần tự qua `send_lock` của TCP.
