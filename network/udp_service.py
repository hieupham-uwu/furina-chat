"""Dịch vụ UDP discovery (HELLO) cho Furina Chat.

Nhiệm vụ:
- Phát gói HELLO định kỳ tới địa chỉ discovery đã chọn, mặc định là 255.255.255.255:9999.
- Lắng nghe HELLO của các peer khác và lưu vào bảng ``_peers``.
- Quét định kỳ, xóa các peer không gửi HELLO trong thời gian quy định.

Hợp đồng với event_bus: gọi ``event_bus.publish(tên_sự_kiện, payload)``.
Các sự kiện phát ra:
- ``peer_updated``: payload gồm peer_id, name, ip, tcp_port, status.
- ``peer_offline``: payload gồm peer_id.
"""

import socket
import threading
import time
from typing import Any, Dict, List, Optional

import config
from network import protocol


class UDPService:
    def __init__(
        self,
        peer_id: str,
        peer_name: str,
        tcp_port: int,
        event_bus: Any = None,
        *,
        discovery_ip: Optional[str] = None,
    ) -> None:
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

        self.peer_id = peer_id
        self.peer_name = peer_name
        self.tcp_port = tcp_port
        self.status = config.STATUS_ONLINE
        self._event_bus = event_bus
        self._hello_target = (
            (discovery_ip, config.UDP_DISCOVERY_PORT)
            if discovery_ip is not None
            else config.UDP_BROADCAST_ADDR
        )

        self._peers: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._sock: Optional[socket.socket] = None
        self._threads: List[threading.Thread] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Mở socket, gửi HELLO đầu tiên và chạy 3 luồng nền."""
        if self._sock is not None:
            return

        self._sock = self._create_socket()
        self._stop_event.clear()

        # Gửi ngay gói HELLO đầu tiên lúc khởi động
        self._send_hello()

        self._threads = [
            threading.Thread(
                target=self._broadcast_loop, name="udp-broadcaster", daemon=True
            ),
            threading.Thread(
                target=self._listen_loop, name="udp-listener", daemon=True
            ),
            threading.Thread(
                target=self._sweep_loop, name="udp-sweeper", daemon=True
            ),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        """Dừng các luồng nền và đóng socket một cách sạch sẽ."""
        self._stop_event.set()

        sock, self._sock = self._sock, None
        if sock is not None:
            # Đóng socket để đánh thức recvfrom() đang chờ trong Listener
            try:
                sock.close()
            except OSError:
                pass

        current = threading.current_thread()
        for thread in self._threads:
            if thread is not current and thread.is_alive():
                thread.join(timeout=config.UDP_JOIN_TIMEOUT)
        self._threads = []

    def set_status(self, status: str) -> None:
        """Đổi trạng thái và phát HELLO ngay lập tức."""
        if status not in config.VALID_STATUSES:
            raise ValueError(f"status must be 'online' or 'away', got {status!r}")

        with self._lock:
            self.status = status

        self._send_hello()

    def get_peer(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Trả về bản sao thông tin peer, hoặc None nếu không tồn tại."""
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer is None:
                return None
            return self._snapshot(peer)

    # ------------------------------------------------------------------
    # Socket & gửi gói tin
    # ------------------------------------------------------------------
    def _create_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Cho phép nhiều phiên chạy trên cùng máy (Linux/macOS hỗ trợ)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass

            sock.bind(("", config.UDP_DISCOVERY_PORT))
            sock.settimeout(config.UDP_RECV_TIMEOUT)
        except OSError:
            sock.close()
            raise
        return sock

    def _send_hello(self) -> None:
        sock = self._sock
        if sock is None:
            return

        with self._lock:
            status = self.status

        data = protocol.pack_udp_hello(self.peer_id, self.peer_name, self.tcp_port, status)
        try:
            sock.sendto(data, self._hello_target)
        except OSError:
            # Mạng chập chờn hoặc chưa kết nối: bỏ qua, luồng vẫn sống
            pass

    def _publish(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(event_name, payload)

    @staticmethod
    def _snapshot(peer: Dict[str, Any]) -> Dict[str, Any]:
        return {field: peer[field] for field in config.PEER_FIELDS}

    # ------------------------------------------------------------------
    # 1. Broadcaster: phát HELLO định kỳ
    # ------------------------------------------------------------------
    def _broadcast_loop(self) -> None:
        # Gói đầu tiên đã gửi trong start(), chờ 1 chu kỳ rồi phát tiếp
        while not self._stop_event.wait(config.HELLO_INTERVAL):
            self._send_hello()

    # ------------------------------------------------------------------
    # 2. Listener: nhận, lọc và cập nhật bảng peer
    # ------------------------------------------------------------------
    def _listen_loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                data, addr = sock.recvfrom(config.UDP_RECV_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                # Socket bị đóng từ stop()
                break
            self._handle_packet(data, addr)

    def _handle_packet(self, data: bytes, addr: Any) -> None:
        hello = protocol.unpack_udp_hello(data)
        if hello is None:
            return
        if hello["peer_id"] == self.peer_id:
            # Bỏ qua gói của chính mình
            return

        peer = {
            "peer_id": hello["peer_id"],
            "name": hello["name"],
            "ip": addr[0],
            "tcp_port": hello["tcp_port"],
            "status": hello["status"],
            "last_seen": time.monotonic(),
        }

        with self._lock:
            old = self._peers.get(peer["peer_id"])
            changed = old is None or any(
                old[field] != peer[field] for field in config.PEER_FIELDS
            )
            self._peers[peer["peer_id"]] = peer

        # Chỉ phát khi peer mới hoặc thông tin/trạng thái thay đổi
        if changed:
            self._publish(config.EVENT_PEER_UPDATED, self._snapshot(peer))

    # ------------------------------------------------------------------
    # 3. Sweeper: xóa peer hết hạn (chạy độc lập, không phụ thuộc recvfrom)
    # ------------------------------------------------------------------
    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(config.UDP_SWEEP_INTERVAL):
            now = time.monotonic()
            expired: List[str] = []

            with self._lock:
                for peer_id, peer in list(self._peers.items()):
                    if now - peer["last_seen"] > config.DISCOVERY_TIMEOUT:
                        expired.append(peer_id)
                for peer_id in expired:
                    del self._peers[peer_id]

            for peer_id in expired:
                self._publish(config.EVENT_PEER_OFFLINE, {"peer_id": peer_id})
