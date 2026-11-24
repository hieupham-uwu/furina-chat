from typing import Tuple

# UDP message types
TYPE_HELLO = "HELLO"

# TCP handshake & chat types
TYPE_HI = "HI"
TYPE_MSG = "MSG"
TYPE_STICKER = "STICKER"
TYPE_BYE = "BYE"

# TCP media types
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
# 1. UDP Discovery
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


# ==============================================================================
# 2. Kết nối TCP
# ==============================================================================
# Địa chỉ lắng nghe mặc định cho TCP server
DEFAULT_TCP_HOST: str = "0.0.0.0"

# Cổng TCP mặc định:
# Đặt bằng 0 để hệ điều hành tự cấp phát cổng trống cho mỗi phiên,
# đảm bảo chạy được nhiều phiên cùng lúc trên một máy với các cổng khác nhau.
DEFAULT_TCP_PORT: int = 0


# ==============================================================================
# 3. Định dạng Frame & Giới hạn dữ liệu
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


# ==============================================================================
# 4. Thời gian chờ (Timeouts)
# ==============================================================================
# Thời hạn tối đa để nhận trọn vẹn một frame HI (giây)
HI_FRAME_TIMEOUT: float = 5.0

# Timeout khi truyền tệp mà không có tiến triển (giây)
FILE_TRANSFER_TIMEOUT: float = 15.0

# Thời gian chờ tối đa để nhận xác nhận (ACK) sau khi đã gửi hết dữ liệu tệp (giây)
FILE_ACK_TIMEOUT: float = 15.0
