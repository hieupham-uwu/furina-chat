# Kiến trúc Furina Chat

Tài liệu mô tả cách dự án LAN chat hoạt động, các module, hàm công khai và luồng dữ liệu giữa hai máy. Các sơ đồ dùng Mermaid, xem được trong VS Code (tiện ích Markdown Preview Mermaid Support), GitHub hoặc [mermaid.live](https://mermaid.live).

## 1. Tổng quan

Furina Chat là ứng dụng chat trong mạng LAN, không cần server trung tâm:

- **Discovery (UDP)**: mỗi phiên gửi `HELLO` broadcast tới cổng `9999` mỗi 3 giây. Peer không gửi `HELLO` trong 10 giây bị coi là offline.
- **Chat (TCP)**: khi mở chat, hai máy bắt tay bằng frame `HI purpose="chat"`, sau đó trao đổi `MSG`, `STICKER`, `BYE`. Mỗi cặp peer giữ tối đa một kết nối chat.
- **Truyền file/ảnh (TCP)**: mỗi lượt gửi mở một kết nối TCP riêng với `HI purpose="media"`, truyền `FILE`/`IMAGE` theo chunk 64 KB, chờ `FILE_OK` rồi mới báo hoàn tất.
- **EventBus**: các dịch vụ mạng không gọi trực tiếp GUI mà đẩy sự kiện vào hàng đợi. GUI/controller đọc hàng đợi trên main thread.

Cổng TCP mặc định là `0` (hệ điều hành tự cấp), cổng thực tế được quảng bá trong `HELLO`, nhờ đó nhiều phiên chạy được trên cùng một máy.

## 2. Cấu trúc thư mục

```text
furina-chat/
├── main.py                  # Entry hiện tại: console test UDP + TCP
├── config.py                # Toàn bộ hằng số giao thức, timeout, sự kiện
├── core/
│   ├── events.py            # Event(name, payload)
│   ├── event_bus.py         # EventBus: publish()/poll() trên Queue
│   ├── models.py            # (chưa có)
│   ├── state.py             # (chưa có nội dung)
│   └── controller.py        # (chưa có nội dung)
├── network/
│   ├── protocol.py          # Framing TCP, pack/unpack HELLO, recv_exact
│   ├── udp_service.py       # Broadcaster, Listener, Sweeper
│   ├── tcp_service.py       # Chat 1-1, handshake, điều phối media
│   └── file_service.py      # Gửi/nhận FILE & IMAGE
├── ui/
│   ├── main_window.py       # Giao diện mẫu, còn giả lập sự kiện
│   ├── peer_sidebar.py
│   ├── chat_panel.py
│   └── sticker_picker.py
├── assets/stickers/<pack>/<sticker_id>.png
├── downloads/               # File nhận được (đã gitignore)
└── tests/
    ├── test_protocol.py
    ├── test_chat.py
    └── test_transfer.py
```

## 3. Kiến trúc tổng thể

```mermaid
flowchart LR
    subgraph UI["ui/ — giao diện mẫu, chưa nối mạng"]
        MW["MainWindow"]
        SB["PeerSidebar"]
        CP["ChatPanel"]
        SP["StickerPicker"]
    end

    subgraph CORE["core/"]
        BUS["EventBus<br/>Queue[Event]"]
        EV["Event(name, payload)"]
        STATE["state.py<br/>(chưa có nội dung)"]
        CTRL["controller.py<br/>(chưa có nội dung)"]
    end

    subgraph NET["network/"]
        UDP["UDPService"]
        TCP["TCPService"]
        FILE["file_service"]
        PROTO["protocol.py"]
    end

    CFG["config.py<br/>hằng số dùng chung"]

    MW --> SB
    MW --> CP
    CP --> SP
    CTRL -. "sẽ cập nhật" .-> STATE
    CTRL -. "sẽ vẽ" .-> MW
    BUS -. "GUI poll bằng after() (dự kiến)" .-> CTRL

    UDP -- "peer_updated<br/>peer_offline" --> BUS
    TCP -- "chat_connected/disconnected<br/>message_sent/received<br/>sticker_sent/received" --> BUS
    FILE -- "transfer_started/progress<br/>finished/failed" --> BUS

    TCP -- "get_peer()" --> UDP
    FILE -- "get_peer()" --> UDP
    TCP -- "HI + MSG/STICKER/BYE" --> PROTO
    UDP -- "HELLO JSON" --> PROTO
    FILE -- "FILE/IMAGE + FILE_OK/ERROR" --> PROTO
    TCP -- "purpose=media" --> FILE
    CFG -.-> UDP
    CFG -.-> TCP
    CFG -.-> FILE
```

## 4. Class và hàm chính

```mermaid
classDiagram
    class Event {
        +str name
        +dict payload
    }

    class EventBus {
        -Queue _queue
        +publish(event_name, payload)
        +poll()
    }

    class UDPService {
        +str peer_id
        +str peer_name
        +int tcp_port
        +str status
        +start()
        +stop()
        +set_status(status)
        +get_peer(peer_id)
        -_broadcast_loop()
        -_listen_loop()
        -_sweep_loop()
        -_handle_packet(data, addr)
        -_send_hello()
    }

    class TCPService {
        +int tcp_port
        +start()
        +stop()
        +open_chat(peer_id)
        +send_message(peer_id, text)
        +send_sticker(peer_id, pack, sticker_id)
        +leave_chat(peer_id)
        -_listen(listener)
        -_accept_chat(sock, local_peer)
        -_handoff_media(sock, peer_id)
        -_register_chat(peer_id, sock, outgoing)
        -_read_chat(peer_id, chat)
        -_disconnect(peer_id, chat, reason)
    }

    class file_service {
        <<module>>
        +configure(peer_id, name, tcp_port, get_peer, bus)
        +send_file(peer_id, path, media_type)
        +handle_incoming(sock, peer_id)
        +stop()
        -_send_worker(transfer_id, peer_id, path, media_type)
        -_safe_filename(raw)
        -_unique_download_path(filename)
    }

    class protocol {
        <<module>>
        +pack_udp_hello(peer_id, name, tcp_port, status)
        +unpack_udp_hello(data)
        +encode_header(header)
        +send_packet(sock, header, payload)
        +recv_header(sock)
        +recv_exact(sock, n)
    }

    EventBus o-- Event
    UDPService ..> EventBus : publish
    TCPService ..> EventBus : publish
    file_service ..> EventBus : publish
    TCPService ..> file_service : handle_incoming
    TCPService ..> protocol
    UDPService ..> protocol
    file_service ..> protocol
```

## 5. Luồng discovery và chat

```mermaid
sequenceDiagram
    autonumber
    participant A as Peer A
    participant UA as UDPService A
    participant UB as UDPService B
    participant TA as TCPService A
    participant TB as TCPService B
    participant BA as EventBus A
    participant BB as EventBus B

    UA->>UB: HELLO broadcast :9999 (3s/lần)
    UB->>BB: peer_updated(A)
    UB->>UA: HELLO
    UA->>BA: peer_updated(B)
    Note over UA,UB: Không nhận HELLO trong 10s<br/>sweeper phát peer_offline

    A->>TA: open_chat(B)
    TA->>UA: get_peer(B)
    UA-->>TA: ip, tcp_port
    TA->>TB: TCP connect + HI purpose=chat
    TB->>TA: HI purpose=chat
    TA->>BA: chat_connected(B)
    TB->>BB: chat_connected(A)

    A->>TA: send_message(B, "Xin chào")
    TA->>TB: MSG frame
    TB->>BB: message_received(A, text)
    B->>TB: send_sticker(A, columbina, id_1)
    TB->>TA: STICKER frame
    TA->>BA: sticker_received

    A->>TA: leave_chat(B)
    TA->>TB: BYE
    TA->>BA: chat_disconnected(left_chat)
    TB->>BB: chat_disconnected(peer_left)
```

## 6. Luồng truyền file/ảnh

```mermaid
sequenceDiagram
    autonumber
    participant C as Controller/UI
    participant FS as file_service máy gửi
    participant UD as UDPService máy gửi
    participant TCP as TCPService máy nhận
    participant FR as file_service máy nhận
    participant D as downloads/

    C->>FS: send_file(peer_id, path, TYPE_FILE)
    FS-->>C: transfer_id (trả ngay)
    FS->>UD: get_peer(peer_id)
    UD-->>FS: ip, tcp_port
    FS->>TCP: TCP connect (socket riêng)
    FS->>TCP: HI purpose=media
    Note over TCP: Media một chiều:<br/>không trả HI, không tạo chat
    TCP->>FR: handle_incoming(sock, peer_id)
    FS->>FR: FILE header (filename, transfer_id, size)

    loop mỗi chunk 64 KB
        FS->>FR: payload
        FR->>D: ghi vào .part
        FS-->>C: transfer_progress
    end

    FR->>D: đổi .part → tên an toàn<br/>(trùng thì "ten (1).ext")
    FR-->>FS: FILE_OK(transfer_id)
    FS-->>C: transfer_finished
    FR-->>C: transfer_finished

    alt lỗi mạng / timeout 15s / lỗi ghi đĩa
        FR->>D: xóa .part
        FR-->>FS: FILE_ERROR
        FS-->>C: transfer_failed
    end
```

## 7. Định dạng dữ liệu trên đường truyền

```text
TCP:  [ "Furina" 6B ][ header_len 4B big-endian ][ JSON UTF-8 ][ payload ... ]
UDP:  [ JSON UTF-8 ]  (một datagram, không có magic/framing)
```

- `MAGIC_BYTES = b"Furina"` giúp phát hiện gói rác ngay từ 6 byte đầu.
- `header_len` nằm trong khoảng `1..65536`; JSON sai schema, sai kiểu, `NaN` hoặc lồng quá sâu đều bị từ chối.
- Chỉ `FILE` và `IMAGE` được mang payload; các frame chat có `payload_size = 0`.
- HELLO UDP gồm `peer_id`, `name`, `tcp_port`, `status`; gói sai kiểu bị bỏ qua.

## 8. Bảng tra nhanh

| Việc muốn làm | Gọi hàm | Sự kiện phát ra |
| --- | --- | --- |
| Bật mạng | `tcp.start()` rồi `udp.start()` | `peer_updated`, `peer_offline` |
| Xem peer | `udp.get_peer(peer_id)` | — |
| Đổi online/away | `udp.set_status("away")` | Gửi HELLO ngay; máy khác nhận `peer_updated` |
| Mở chat | `tcp.open_chat(peer_id)` | `chat_connected` hoặc `operation_failed` |
| Gửi tin | `tcp.send_message(peer_id, text)` | `message_sent` (gửi), `message_received` (nhận) |
| Gửi sticker | `tcp.send_sticker(peer_id, pack, id)` | `sticker_sent` / `sticker_received` |
| Đóng chat | `tcp.leave_chat(peer_id)` | `chat_disconnected` |
| Gửi file/ảnh | `file_service.send_file(peer_id, path, TYPE_FILE/IMAGE)` | Trả `transfer_id`; `transfer_*` |
| Nhận file | Tự động qua TCP → `handle_incoming` | `transfer_started/progress/finished/failed` |
| GUI lấy sự kiện | `event_bus.poll()` trong `after(50)` | `Event(name, payload)` |

## 9. Mô hình luồng

- **UDP**: một socket, ba luồng nền — Broadcaster (3 giây), Listener, Sweeper (quét mỗi 1 giây, hết hạn sau 10 giây).
- **TCP**: một luồng `accept`; mỗi kết nối một worker. Chat có luồng đọc riêng, ghi được bảo vệ bằng `send_lock`. Kết nối media được bàn giao nguyên socket cho `file_service`.
- **File**: mỗi lượt gửi chạy trong một luồng nền; phía nhận chạy trên worker TCP, ghi `.part` rồi mới đổi tên.
- **GUI dự kiến**: chỉ đọc `EventBus` trên main thread bằng `after()`, không gọi socket trực tiếp.

## 10. Xử lý lỗi và timeout

| Tình huống | Cơ chế |
| --- | --- |
| Gói rác / header quá lớn | Kiểm tra magic, giới hạn 64 KB, đóng socket |
| HI đến chậm | Hạn chót 5 giây cho toàn bộ frame HI |
| Peer crash không gửi BYE | `recv()` trả `b""` hoặc `ConnectionResetError` → `chat_disconnected` |
| Peer vừa offline | `get_peer()` trả `None` → `operation_failed`, GUI báo lỗi |
| Mất mạng khi truyền file | Timeout 15 giây, xóa `.part`, gửi `FILE_ERROR`, phát `transfer_failed` |
| Gửi file trùng tên | Tự chọn `ten (1).ext`, `ten (2).ext`… |
| Tên file nguy hiểm | Bỏ đường dẫn/ký tự cấm, chặn tên thiết bị Windows (`CON`, `NUL`…) |
| Hai bên cùng mở chat | Giữ kết nối do peer có `peer_id` nhỏ hơn khởi tạo |

## 11. Hiện trạng tích hợp

- **Đã chạy thật**: UDP discovery, đổi trạng thái, chat 1-1, sticker, BYE, truyền file/ảnh qua kết nối media.
- **Đã có test**: 21 test (`test_protocol`, `test_chat`, `test_transfer`).
- **Chưa nối**: `core/state.py`, `core/controller.py`, `core/models.py` và GUI thật; `main.py` hiện vẫn là console test.
