import json
import socket
import struct

from typing import Any, Dict, Optional

import config

# {
#     "type": "HELLO",
#     "peer_id": "550e8400-e29b-41d4-a716-446655440000",
#     "name": "Quan",
#     "tcp_port": 5000,
#     "status": "online",
# }


def pack_udp_hello(
    peer_id: str,
    name: str,
    tcp_port: int,
    status: str = config.STATUS_ONLINE,
) -> bytes:

    if not isinstance(peer_id, str) or not peer_id.strip():
        raise ValueError("peer_id must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if (
        not isinstance(tcp_port, int)
        or isinstance(tcp_port, bool)
        or not 1 <= tcp_port <= 65535
    ):
        raise ValueError(f"tcp_port must be an int in 1..65535, got {tcp_port!r}")
    if status not in config.VALID_STATUSES:
        raise ValueError(f"status must be 'online' or 'away', got {status!r}")

    payload = {
        "type": config.TYPE_HELLO,
        "peer_id": peer_id,
        "name": name,
        "tcp_port": tcp_port,
        "status": status,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def unpack_udp_hello(data: bytes) -> Optional[Dict[str, Any]]:
    try:
        msg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(msg, dict) or msg.get("type") != config.TYPE_HELLO:
        return None

    peer_id = msg.get("peer_id")
    name = msg.get("name")
    tcp_port = msg.get("tcp_port")
    status = msg.get("status")

    if not isinstance(peer_id, str) or not peer_id.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    if (
        not isinstance(tcp_port, int)
        or isinstance(tcp_port, bool)
        or not 1 <= tcp_port <= 65535
    ):
        return None
    if status not in config.VALID_STATUSES:
        return None

    return {
        "type": config.TYPE_HELLO,
        "peer_id": peer_id,
        "name": name,
        "tcp_port": tcp_port,
        "status": status,
    }

def recv_exact(sock: socket.socket, n: int) -> bytes:
    if n < 0:
        raise ValueError("Byte count must be non-negative")

    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError(f"Connection closed after {len(data)} of {n} bytes")
        data.extend(chunk)

    return bytes(data)


def _validate_tcp_header(header: Any) -> None:
    if not isinstance(header, dict):
        raise ValueError("TCP header must be a JSON object")

    frame_type = header.get("type")
    if not isinstance(frame_type, str) or frame_type not in config.ALL_TCP_TYPES:
        raise ValueError("Invalid TCP frame type")

    size = header.get("payload_size")
    if type(size) is not int or size < 0:
        raise ValueError("payload_size must be a non-negative integer")

    if frame_type not in config.MEDIA_DATA_TYPES and size != 0:
        raise ValueError("Only FILE and IMAGE can carry a payload")


def encode_header(header: Dict[str, Any]) -> bytes:
    _validate_tcp_header(header)
    raw = json.dumps(header, ensure_ascii=False, allow_nan=False).encode("utf-8")

    if not 1 <= len(raw) <= config.MAX_JSON_HEADER_SIZE:
        raise ValueError("Invalid TCP header length")

    return config.MAGIC_BYTES + struct.pack("!I", len(raw)) + raw


def send_packet(
    sock: socket.socket, header: Dict[str, Any], payload: bytes = b""
) -> None:
    prefix_and_header = encode_header(header)
    if len(payload) != header["payload_size"]:
        raise ValueError("Payload length does not match payload_size")

    sock.sendall(prefix_and_header + payload)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def recv_header(sock: socket.socket) -> Dict[str, Any]:
    magic = recv_exact(sock, len(config.MAGIC_BYTES))
    if magic != config.MAGIC_BYTES:
        raise ValueError("Invalid TCP magic bytes")

    (header_len,) = struct.unpack("!I", recv_exact(sock, 4))
    if not 1 <= header_len <= config.MAX_JSON_HEADER_SIZE:
        raise ValueError("Invalid TCP header length")

    raw = recv_exact(sock, header_len)
    try:
        header = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except RecursionError as exc:
        raise ValueError("TCP header JSON is nested too deeply") from exc

    _validate_tcp_header(header)
    return header