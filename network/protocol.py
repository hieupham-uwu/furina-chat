import json
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
