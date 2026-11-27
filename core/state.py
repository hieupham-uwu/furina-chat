import socket
import threading
import uuid
from typing import Any, Dict, List, Optional
import config


def _default_peer_name() -> str:
    host = socket.gethostname().strip()
    return host if host else "Peer"


class AppState:
    def __init__(
        self, my_name: Optional[str] = None, my_peer_id: Optional[str] = None
    ) -> None:
        self.lock = threading.Lock()
        self.my_peer_id: str = my_peer_id or str(uuid.uuid4())
        self.my_name: str = (
            my_name.strip()
            if isinstance(my_name, str) and my_name.strip()
            else _default_peer_name()
        )
        self.my_status: str = getattr(config, "STATUS_ONLINE", "online")
        self.my_tcp_port: int = getattr(config, "DEFAULT_TCP_PORT", 5000)

        self.peers: Dict[str, Dict[str, Any]] = {}
        self.chat_history: Dict[str, List[Dict[str, Any]]] = {}
        self.unread_counts: Dict[str, int] = {}
        self.drafts: Dict[str, str] = {}
        self.transfers: Dict[str, Dict[str, Any]] = {}
        self.last_activity: Dict[str, float] = {}
        self.active_peer_id: Optional[str] = None


state = AppState()
