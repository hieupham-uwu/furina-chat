import threading
import uuid


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.my_peer_id = str(uuid.uuid4())
        self.my_name = "Minh Anh"
        self.my_status = "online"
        self.my_tcp_port = 5000

        # {peer_id: {"peer_id": ..., "name": ..., "ip": ..., "tcp_port": ..., "status": "online"|"offline"}}
        self.peers = {}
        # {peer_id: [msg_dict, ...]}
        self.chat_history = {}
        # {peer_id: int}
        self.unread_counts = {}
        # {peer_id: "chữ đang gõ dở"}
        self.drafts = {}
        # {transfer_id: dict}
        self.transfers = {}
        self.active_peer_id = None


state = AppState()