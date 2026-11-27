from typing import Tuple


# ==============================================================================
# 1. Loại message dùng chung (UDP + TCP)
# ==============================================================================
# UDP discovery
TYPE_HELLO = "HELLO"

# TCP handshake & chat
TYPE_HI = "HI"
TYPE_MSG = "MSG"
TYPE_STICKER = "STICKER"
TYPE_BYE = "BYE"

# TCP media
TYPE_FILE = "FILE"
TYPE_IMAGE = "IMAGE"
TYPE_FILE_OK = "FILE_OK"
TYPE_FILE_ERROR = "FILE_ERROR"

# Nhóm hợp lệ để kiểm tra nhanh khi validate frame
CHAT_TYPES = {TYPE_MSG, TYPE_STICKER, TYPE_BYE}
MEDIA_DATA_TYPES = {TYPE_FILE, TYPE_IMAGE}
MEDIA_ACK_TYPES = {TYPE_FILE_OK, TYPE_FILE_ERROR}
ALL_TCP_TYPES = {TYPE_HI} | CHAT_TYPES | MEDIA_DATA_TYPES | MEDIA_ACK_TYPES


# ==============================================================================
# 2. Trạng thái peer & tên sự kiện (event_bus)
# ==============================================================================
STATUS_ONLINE = "online"
STATUS_AWAY = "away"
VALID_STATUSES = (STATUS_ONLINE, STATUS_AWAY)

EVENT_PEER_UPDATED = "peer_updated"
EVENT_PEER_OFFLINE = "peer_offline"

# Sự kiện truyền file
EVENT_TRANSFER_STARTED = "transfer_started"
EVENT_TRANSFER_PROGRESS = "transfer_progress"
EVENT_TRANSFER_FINISHED = "transfer_finished"
EVENT_TRANSFER_FAILED = "transfer_failed"
EVENT_TRANSFER_CANCELLED = "transfer_cancelled"

# Các trường công khai của một peer (bỏ last_seen khi trả ra ngoài)
PEER_FIELDS: Tuple[str, ...] = ("peer_id", "name", "ip", "tcp_port", "status")


# ==============================================================================
# 3. UDP Discovery
# ==============================================================================
# Cổng lắng nghe và gửi gói tin UDP discovery
UDP_DISCOVERY_PORT: int = 9999

# Địa chỉ IP broadcast dùng cho UDP discovery
UDP_BROADCAST_IP: str = "255.255.255.255"

# Bộ địa chỉ đầy đủ (IP, Port) cho UDP broadcast
UDP_BROADCAST_ADDR: Tuple[str, int] = (UDP_BROADCAST_IP, UDP_DISCOVERY_PORT)

# Chu kỳ phát gói tin HELLO (giây)
HELLO_INTERVAL: float = 3.0

# Thời gian hết hạn discovery kể từ gói HELLO hợp lệ cuối cùng (giây)
DISCOVERY_TIMEOUT: float = 10.0

# Chu kỳ quét peer hết hạn của luồng Sweeper (giây)
UDP_SWEEP_INTERVAL: float = 1.0

# Kích thước bộ đệm đọc gói UDP (byte)
UDP_RECV_BUFFER_SIZE: int = 4096

# Timeout của socket UDP để Listener thường xuyên kiểm tra tín hiệu dừng (giây)
UDP_RECV_TIMEOUT: float = 1.0

# Thời gian chờ tối đa khi join các luồng nền của UDPService (giây)
UDP_JOIN_TIMEOUT: float = 2.0


# ==============================================================================
# 4. Kết nối TCP
# ==============================================================================
# Địa chỉ lắng nghe mặc định cho TCP server
DEFAULT_TCP_HOST: str = "0.0.0.0"

# Cổng TCP mặc định:
# Đặt bằng 0 để hệ điều hành tự cấp phát cổng trống cho mỗi phiên,
# đảm bảo chạy được nhiều phiên cùng lúc trên một máy với các cổng khác nhau.
DEFAULT_TCP_PORT: int = 0


# ==============================================================================
# 5. Định dạng Frame & Giới hạn dữ liệu
# ==============================================================================
# Chuỗi byte nhận diện giao thức (Magic bytes), dài 6 byte
MAGIC_BYTES: bytes = b"Furina"
MAGIC_BYTES_LENGTH: int = len(MAGIC_BYTES)  # 6 byte

# Kích thước tối đa của phần JSON header (byte)
MAX_JSON_HEADER_SIZE: int = 65_536  # 64 KiB

# Độ dài tối đa của nội dung tin nhắn trong trường "text" (ký tự)
MAX_MESSAGE_LENGTH: int = 4_000

# Kích thước tối đa của mỗi khối (chunk) khi đọc hoặc ghi tệp (byte)
FILE_CHUNK_SIZE: int = 65_536  # 64 KiB

# Khoảng thời gian tối thiểu giữa hai lần cập nhật tiến độ (giây)
FILE_PROGRESS_INTERVAL: float = 0.2


# ==============================================================================
# 6. Truyền file (media)
# ==============================================================================
# Purpose của gói HI: "chat" mở kết nối chat, "media" mở kết nối truyền file
HI_PURPOSE_CHAT = "chat"
HI_PURPOSE_MEDIA = "media"

# Hướng truyền dùng trong payload sự kiện
TRANSFER_DIRECTION_SEND = "send"
TRANSFER_DIRECTION_RECEIVE = "receive"

# Tên thư mục nhận file, đặt cạnh main.py
DOWNLOADS_DIR_NAME = "downloads"

# Thời gian chờ tối đa khi join luồng gửi file (giây)
FILE_JOIN_TIMEOUT: float = 2.0

# Số lần thử mở kết nối media khi connect thất bại tạm thời
FILE_CONNECT_ATTEMPTS: int = 3

# Thời gian chờ trước mỗi lần thử lại, nhân với số thứ tự lần thử (giây)
FILE_RETRY_BACKOFF: float = 0.5


# ==============================================================================
# 7. Thời gian chờ (Timeouts)
# ==============================================================================
# Thời hạn tối đa để nhận trọn vẹn một frame HI (giây)
HI_FRAME_TIMEOUT: float = 5.0

# Thời gian tối đa dành cho việc gửi BYE khi thoát ứng dụng (giây)
CHAT_SHUTDOWN_TIMEOUT: float = 0.75

# Timeout khi truyền tệp mà không có tiến triển (giây)
FILE_TRANSFER_TIMEOUT: float = 15.0

# Thời gian chờ tối đa để nhận xác nhận (ACK) sau khi đã gửi hết dữ liệu tệp (giây)
FILE_ACK_TIMEOUT: float = 15.0
