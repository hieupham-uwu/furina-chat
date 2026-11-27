"""Truyền/nhận FILE và IMAGE trên kết nối TCP riêng (purpose="media").

Tích hợp với các thành viên khác:
- C (controller/UI) gọi ``configure(...)`` một lần lúc khởi động, sau đó
  dùng ``send_file(peer_id, path, media_type)`` và nghe event_bus.
- B (tcp_service) đọc gói HI; nếu ``purpose == "media"`` thì gọi
  ``handle_incoming(sock, peer_id)`` và không gửi HI trả lời: gói HI media
  chỉ đi một chiều, frame kế tiếp trên socket là FILE/IMAGE.

Sự kiện phát ra: transfer_started, transfer_progress, transfer_finished,
transfer_failed (xem config.EVENT_TRANSFER_*).
"""

import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import UUID

import config
from network.protocol import encode_header, recv_exact, recv_header, send_packet

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / config.DOWNLOADS_DIR_NAME

_FORBIDDEN_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

_lock = Lock()
_rename_lock = Lock()
_sockets = set()
_send_transfers = {}
_stop_event = threading.Event()
_local_peer: Optional[Tuple[str, str, int]] = None
_get_peer: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
_bus: Any = None
# Địa chỉ peer lần cuối còn thấy trong discovery, để gửi file khi peer đã hết hạn.
_peer_cache: Dict[str, Dict[str, Any]] = {}


@dataclass
class _SendTransfer:
    cancelled: threading.Event = field(default_factory=threading.Event)
    sock: Optional[socket.socket] = None
    thread: Optional[threading.Thread] = None
    can_cancel: bool = True


# ----------------------------------------------------------------------
# Cấu hình & public API
# ----------------------------------------------------------------------
def configure(peer_id, peer_name, tcp_port, get_peer, event_bus):
    """Nạp thông tin cục bộ và phụ thuộc; gọi một lần trước khi dùng."""
    if not isinstance(peer_id, str) or not peer_id.strip():
        raise ValueError("peer_id must be a non-empty string")
    if not isinstance(peer_name, str) or not peer_name.strip():
        raise ValueError("peer_name must be a non-empty string")
    if (
        not isinstance(tcp_port, int)
        or isinstance(tcp_port, bool)
        or not 1 <= tcp_port <= 65535
    ):
        raise ValueError(f"tcp_port must be an int in 1..65535, got {tcp_port!r}")

    global _local_peer, _get_peer, _bus
    _local_peer = (peer_id, peer_name, tcp_port)
    _get_peer = get_peer
    _bus = event_bus
    with _lock:
        _peer_cache.clear()
    _stop_event.clear()


def send_file(peer_id, path, media_type=config.TYPE_FILE):
    """Bắt đầu gửi file trong luồng nền và trả về transfer_id ngay."""
    if _local_peer is None or _get_peer is None or _bus is None:
        raise RuntimeError("file_service chưa được configure()")
    if _stop_event.is_set():
        raise RuntimeError("file_service đã stop()")
    if not isinstance(media_type, str):
        raise ValueError("media_type must be FILE or IMAGE")
    media_type = media_type.upper()
    if media_type not in config.MEDIA_DATA_TYPES:
        raise ValueError("media_type must be FILE or IMAGE")

    file_path = os.path.abspath(os.fspath(path))
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    transfer_id = str(uuid.uuid4())
    transfer = _SendTransfer()
    transfer.thread = threading.Thread(
        target=_send_worker,
        args=(transfer_id, transfer, peer_id, file_path, media_type),
        name=f"file-send-{transfer_id[:8]}",
        daemon=True,
    )
    with _lock:
        if _stop_event.is_set():
            raise RuntimeError("Dịch vụ truyền tệp đã dừng")
        _send_transfers[transfer_id] = transfer
        try:
            transfer.thread.start()
        except RuntimeError:
            del _send_transfers[transfer_id]
            raise
    return transfer_id


def cancel_send(transfer_id):
    """Dừng lượt gửi nếu máy gửi chưa bắt đầu chuyển khối dữ liệu cuối."""
    with _lock:
        transfer = _send_transfers.get(transfer_id)
        if transfer is None or not transfer.can_cancel or transfer.cancelled.is_set():
            return False
        transfer.cancelled.set()
        sock = transfer.sock
    if sock is not None:
        _close_socket(sock)
    return True


def handle_incoming(sock, peer_id):
    """Nhận một FILE/IMAGE trên socket mà B đã bàn giao."""
    transfer_id = None
    filename = None
    media_type = None
    total_bytes = 0
    part_path = None
    direction = config.TRANSFER_DIRECTION_RECEIVE

    try:
        with _lock:
            _sockets.add(sock)
        if _stop_event.is_set():
            return

        sock.settimeout(config.FILE_TRANSFER_TIMEOUT)
        header = recv_header(sock)

        if header["type"] not in config.MEDIA_DATA_TYPES:
            raise ValueError("Frame không phải FILE hoặc IMAGE")
        media_type = header["type"]

        transfer_id = header.get("transfer_id")
        if not isinstance(transfer_id, str):
            raise ValueError("transfer_id không hợp lệ")
        UUID(transfer_id)

        filename = _safe_filename(header.get("filename"))
        total_bytes = header["payload_size"]

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        part_path = DOWNLOAD_DIR / f".{transfer_id}.part"

        details = {
            "transfer_id": transfer_id,
            "peer_id": peer_id,
            "direction": direction,
            "filename": filename,
            "total_bytes": total_bytes,
            "media_type": media_type,
        }
        _publish(config.EVENT_TRANSFER_STARTED, details)

        received = 0
        last_update = float("-inf")
        with open(part_path, "wb") as file:
            while received < total_bytes:
                size = min(config.FILE_CHUNK_SIZE, total_bytes - received)
                chunk = recv_exact(sock, size)
                file.write(chunk)
                received += len(chunk)
                last_update = _publish_progress(details, received, last_update)

        with _rename_lock:
            target = _unique_download_path(filename)
            os.replace(part_path, target)
        part_path = None

        send_packet(sock, {
            "type": config.TYPE_FILE_OK,
            "transfer_id": transfer_id,
            "payload_size": 0,
        })
        _publish(config.EVENT_TRANSFER_FINISHED, {
            "transfer_id": transfer_id,
            "peer_id": peer_id,
            "direction": direction,
            "filename": filename,
            "total_bytes": total_bytes,
            "media_type": media_type,
            "local_path": str(target),
        })
    except (OSError, EOFError, ValueError, TimeoutError) as error:
        if part_path is not None:
            try:
                part_path.unlink()
            except OSError:
                pass

        reason = str(error)
        message = "Không nhận được tệp."
        if isinstance(error, TimeoutError):
            reason = "Quá thời gian chờ dữ liệu từ máy gửi"
            message = reason + "."
        elif isinstance(error, (EOFError, ConnectionError)):
            message = "Lượt nhận tệp bị gián đoạn."
        if not reason:
            reason = error.__class__.__name__

        if transfer_id is not None and not _stop_event.is_set():
            _send_error(sock, transfer_id, reason)
        if not _stop_event.is_set():
            _publish(config.EVENT_TRANSFER_FAILED, {
                "transfer_id": transfer_id,
                "peer_id": peer_id,
                "direction": direction,
                "filename": filename,
                "media_type": media_type,
                "total_bytes": total_bytes,
                "reason": reason,
                "message": message,
            })
    finally:
        _close_socket(sock)
        with _lock:
            _sockets.discard(sock)


def stop():
    """Đóng mọi socket media và chờ các luồng gửi kết thúc."""
    _stop_event.set()

    with _lock:
        sockets = list(_sockets)
        transfers = list(_send_transfers.values())
        for transfer in transfers:
            transfer.cancelled.set()

    for sock in sockets:
        _close_socket(sock)

    current = threading.current_thread()
    for transfer in transfers:
        thread = transfer.thread
        if thread is not current and thread.is_alive():
            thread.join(timeout=config.FILE_JOIN_TIMEOUT)

    with _lock:
        _sockets.clear()
        _send_transfers.clear()


# ----------------------------------------------------------------------
# Phía gửi
# ----------------------------------------------------------------------
def remember_peer(peer_id, ip, tcp_port):
    """Ghi nhớ địa chỉ peer để vẫn gửi được khi discovery đã hết hạn."""
    if not isinstance(ip, str) or not ip.strip():
        return
    if type(tcp_port) is not int or not 1 <= tcp_port <= 65535:
        return
    with _lock:
        _peer_cache[peer_id] = {"ip": ip, "tcp_port": tcp_port}


def _resolve_peer(peer_id):
    """Dùng địa chỉ hiện tại hoặc địa chỉ đã ghi nhớ của peer."""
    peer = _get_peer(peer_id)
    if peer:
        remember_peer(peer_id, peer["ip"], peer["tcp_port"])
        return peer

    with _lock:
        cached = _peer_cache.get(peer_id)
    if cached:
        return dict(cached)
    raise ValueError("Không tìm thấy peer trong danh sách discovery")


def _connect_media(peer_id, local_peer, transfer):
    """Mở kết nối media, thử lại khi lỗi mạng tạm thời."""
    local_id, local_name, local_port = local_peer
    max_attempts = max(1, config.FILE_CONNECT_ATTEMPTS)
    for attempt in range(1, max_attempts + 1):
        peer = _resolve_peer(peer_id)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with _lock:
            if _stop_event.is_set() or transfer.cancelled.is_set():
                sock.close()
                raise InterruptedError("Lượt gửi đã dừng")
            _sockets.add(sock)
            transfer.sock = sock
        try:
            sock.settimeout(config.HI_FRAME_TIMEOUT)
            sock.connect((peer["ip"], int(peer["tcp_port"])))
            send_packet(sock, {
                "type": config.TYPE_HI,
                "peer_id": local_id,
                "name": local_name,
                "tcp_port": local_port,
                "purpose": config.HI_PURPOSE_MEDIA,
                "payload_size": 0,
            })
            return sock
        except (OSError, ValueError, KeyError, TypeError) as error:
            _close_socket(sock)
            with _lock:
                _sockets.discard(sock)
                transfer.sock = None
            if (
                not isinstance(error, OSError)
                or attempt == max_attempts
                or transfer.cancelled.wait(config.FILE_RETRY_BACKOFF * attempt)
            ):
                raise


def _send_worker(transfer_id, transfer, peer_id, file_path, media_type):
    filename = os.path.basename(file_path)
    sock = None
    details = {
        "transfer_id": transfer_id, "peer_id": peer_id, "filename": filename,
        "direction": config.TRANSFER_DIRECTION_SEND, "media_type": media_type, "total_bytes": 0,
    }
    failure_message = "Không đọc được tệp để gửi."

    try:
        total_bytes = os.path.getsize(file_path)
        details["total_bytes"] = total_bytes
        failure_message = "Không kết nối được với máy nhận tệp."
        sock = _connect_media(peer_id, _local_peer, transfer)
        _publish(config.EVENT_TRANSFER_STARTED, details)

        failure_message = "Đường truyền gửi tệp bị gián đoạn."
        sock.settimeout(config.FILE_TRANSFER_TIMEOUT)
        if total_bytes == 0:
            _begin_final_chunk(transfer)
        sock.sendall(encode_header({
            "type": media_type,
            "filename": filename,
            "transfer_id": transfer_id,
            "payload_size": total_bytes,
        }))

        sent = 0
        last_update = float("-inf")
        with open(file_path, "rb") as file:
            while sent < total_bytes:
                size = min(config.FILE_CHUNK_SIZE, total_bytes - sent)
                chunk = file.read(size)
                if not chunk:
                    raise ValueError("Tệp đã thay đổi trong lúc gửi")
                if sent + len(chunk) == total_bytes:
                    _begin_final_chunk(transfer)
                pending = memoryview(chunk)
                while pending:
                    if transfer.cancelled.is_set():
                        raise InterruptedError("Lượt gửi đã dừng")
                    written = sock.send(pending)
                    if not written:
                        raise EOFError("Kết nối gửi tệp đã đóng")
                    sent += written
                    pending = pending[written:]
                last_update = _publish_progress(details, sent, last_update)

        failure_message = "Không nhận được xác nhận hợp lệ từ máy nhận tệp."
        sock.settimeout(config.FILE_ACK_TIMEOUT)
        try:
            ack = recv_header(sock)
        except (socket.timeout, TimeoutError) as error:
            raise ValueError("Chưa nhận được xác nhận từ máy nhận") from error

        if ack.get("transfer_id") != transfer_id:
            raise ValueError("Xác nhận không khớp transfer_id")
        if ack["type"] == config.TYPE_FILE_ERROR:
            failure_message = "Máy nhận không lưu được tệp."
            raise ValueError(ack.get("reason") or "Máy nhận báo lỗi")
        if ack["type"] != config.TYPE_FILE_OK:
            raise ValueError("Phản hồi xác nhận không hợp lệ")

        _publish(config.EVENT_TRANSFER_FINISHED, details)
    except (OSError, EOFError, ValueError, KeyError, TypeError) as error:
        with _lock:
            transfer.can_cancel = False
            cancelled = transfer.cancelled.is_set()
        if not _stop_event.is_set():
            if cancelled:
                _publish(config.EVENT_TRANSFER_CANCELLED, details)
            else:
                _publish(config.EVENT_TRANSFER_FAILED, {
                    **details, "reason": str(error) or error.__class__.__name__, "message": failure_message,
                })
    finally:
        if sock is not None:
            _close_socket(sock)
            with _lock:
                _sockets.discard(sock)
        with _lock:
            _send_transfers.pop(transfer_id, None)


# ----------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------
def _publish(event_name, payload):
    if _bus is not None:
        _bus.publish(event_name, payload)


def _publish_progress(details, done, last_update):
    now = time.monotonic()
    if done == details["total_bytes"] or now - last_update >= config.FILE_PROGRESS_INTERVAL:
        _publish(config.EVENT_TRANSFER_PROGRESS, {**details, "bytes_done": done})
        return now
    return last_update


def _begin_final_chunk(transfer):
    with _lock:
        if transfer.cancelled.is_set():
            raise InterruptedError("Lượt gửi đã dừng")
        transfer.can_cancel = False


def _safe_filename(raw):
    """Lọc tên file nhận từ mạng để không thoát khỏi downloads/."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Tên file không hợp lệ")

    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        ch for ch in name
        if ch not in _FORBIDDEN_CHARS and ord(ch) >= 32 and ord(ch) != 127
    )
    name = name.strip().rstrip(". ").strip()
    if name in ("", ".", ".."):
        raise ValueError("Tên file không hợp lệ")

    stem, dot, _ = name.rpartition(".")
    base = stem if dot else name
    if base.upper() in _RESERVED_NAMES:
        name = "_" + name

    if len(name) > 200:
        root, ext = os.path.splitext(name)
        if len(ext) > 190:
            ext = ""
            root = name
        name = root[: 200 - len(ext)] + ext
    return name


def _unique_download_path(filename):
    target = DOWNLOAD_DIR / filename
    if not target.exists():
        return target

    stem, suffix = os.path.splitext(filename)
    index = 1
    while True:
        target = DOWNLOAD_DIR / f"{stem} ({index}){suffix}"
        if not target.exists():
            return target
        index += 1


def _send_error(sock, transfer_id, reason):
    try:
        send_packet(sock, {
            "type": config.TYPE_FILE_ERROR,
            "transfer_id": transfer_id,
            "reason": reason,
            "payload_size": 0,
        })
    except (OSError, ValueError):
        pass


def _close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
