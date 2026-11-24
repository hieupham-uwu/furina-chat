"""Dịch vụ TCP chat cho Furina Chat.

Nhiệm vụ:
- Lắng nghe kết nối, trao đổi HI và lưu một kết nối cho mỗi peer_id.
- Gửi, nhận MSG và đóng kết nối khi có BYE hoặc lỗi socket.
- Lấy địa chỉ của peer qua get_peer(peer_id) từ UDP discovery.

Hợp đồng với event_bus: gọi event_bus.publish(tên_sự_kiện, payload).
Các sự kiện phát ra: chat_connected, chat_disconnected, message_sent,
message_received và operation_failed.
"""

import socket
import time
from threading import Lock, Thread
from uuid import UUID

import config
from network.protocol import recv_header, send_packet


def send_chat_hi(sock, peer_id, name, tcp_port):
    send_packet(sock, {
        "type": config.TYPE_HI,
        "peer_id": peer_id,
        "name": name,
        "tcp_port": tcp_port,
        "purpose": "chat",
        "payload_size": 0,
    })


def recv_chat_hi(sock):
    previous_timeout = sock.gettimeout()

    # Mọi lần đọc của cùng một frame HI dùng chung một hạn chót.
    deadline = time.monotonic() + config.HI_FRAME_TIMEOUT
    try:
        header = recv_header(sock, deadline=deadline)
    finally:
        sock.settimeout(previous_timeout)

    if header["type"] != config.TYPE_HI or header.get("purpose") != "chat":
        raise ValueError("Expected a chat HI frame")

    peer_id = header.get("peer_id")
    if not isinstance(peer_id, str):
        raise ValueError("peer_id must be a UUID string")
    UUID(peer_id)

    name = header.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Peer name must be a non-empty string")

    port = header.get("tcp_port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid TCP port")

    return header


def _connect_and_exchange_hi(sock, address, local_peer, expected_peer_id):
    local_id, local_name, local_port = local_peer
    sock.settimeout(config.HI_FRAME_TIMEOUT)
    sock.connect(address)

    send_chat_hi(sock, local_id, local_name, local_port)
    reply = recv_chat_hi(sock)
    if reply["peer_id"] != expected_peer_id:
        raise ValueError("The peer ID in HI does not match")

    sock.settimeout(None)


def open_chat(address, local_peer, expected_peer_id, bus):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        _connect_and_exchange_hi(sock, address, local_peer, expected_peer_id)
    except (OSError, EOFError, ValueError) as error:
        sock.close()
        bus.publish("operation_failed", {
            "operation": "open_chat",
            "peer_id": expected_peer_id,
            "reason": str(error),
        })
        raise

    bus.publish("chat_connected", {"peer_id": expected_peer_id})
    return sock


def _handle_incoming(sock, local_peer, bus, on_chat):
    local_id, local_name, local_port = local_peer

    with sock:
        peer_id = None

        try:
            greeting = recv_chat_hi(sock)
            peer_id = greeting["peer_id"]
            send_chat_hi(sock, local_id, local_name, local_port)
        except (OSError, EOFError, ValueError) as error:
            bus.publish("operation_failed", {
                "operation": "accept_chat",
                "peer_id": peer_id,
                "reason": str(error),
            })
            return

        bus.publish("chat_connected", {"peer_id": peer_id})

        try:
            on_chat(sock, peer_id)
        except (OSError, EOFError, ValueError) as error:
            bus.publish("operation_failed", {
                "operation": "handle_chat",
                "peer_id": peer_id,
                "reason": str(error),
            })


def serve_chats(listener, local_peer, bus, stop, on_chat):
    # Định kỳ thoát khỏi accept() để kiểm tra tín hiệu dừng.
    listener.settimeout(0.2)

    while not stop.is_set():
        try:
            sock, _ = listener.accept()
        except socket.timeout:
            continue

        worker = Thread(
            target=_handle_incoming,
            args=(sock, local_peer, bus, on_chat),
            daemon=True,
        )
        worker.start()


def _check_chat_text(text):
    if not isinstance(text, str):
        raise ValueError("Message text must be a string")
    if len(text) > config.MAX_MESSAGE_LENGTH:
        raise ValueError("Message is too long")


def send_chat_message(sock, peer_id, text, bus):
    _check_chat_text(text)

    send_packet(sock, {
        "type": config.TYPE_MSG,
        "text": text,
        "payload_size": 0,
    })
    bus.publish("message_sent", {"peer_id": peer_id, "text": text})


def receive_chat_message(sock, peer_id, bus):
    header = recv_header(sock)
    if header["type"] != config.TYPE_MSG:
        raise ValueError("Expected a MSG frame")

    text = header.get("text")
    _check_chat_text(text)
    bus.publish("message_received", {"peer_id": peer_id, "text": text})
    return text


class _ChatConnection:
    def __init__(self, sock, outgoing):
        self.sock = sock
        self.outgoing = outgoing
        # Chỉ một luồng được ghi frame lên socket tại một thời điểm.
        self.send_lock = Lock()


class TCPService:
    def __init__(
        self, peer_id, peer_name, get_peer, event_bus,
        host=config.DEFAULT_TCP_HOST, port=config.DEFAULT_TCP_PORT,
    ):
        self.peer_id = peer_id
        self.peer_name = peer_name
        self.tcp_port = port
        self._host = host
        self._port = port
        self._get_peer = get_peer
        self._bus = event_bus

        self._lock = Lock()
        self._chats = {}      # peer_id -> kết nối đang dùng
        self._opening = {}    # peer_id -> socket đang chủ động kết nối
        self._sockets = set()  # Cả socket đang bắt tay, để stop() cũng đóng được
        self._listener = None
        self._listener_thread = None

    # ------------------------------------------------------------------
    # Mở, gửi và đóng kết nối
    # ------------------------------------------------------------------
    def start(self):
        """Bắt đầu lắng nghe và trả về cổng TCP thực tế."""
        with self._lock:
            if self._listener is not None:
                return self.tcp_port

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.bind((self._host, self._port))
                listener.listen()
                listener.settimeout(0.2)
            except OSError:
                listener.close()
                raise

            self.tcp_port = listener.getsockname()[1]
            self._listener = listener
            self._listener_thread = Thread(
                target=self._listen, args=(listener,), daemon=True
            )
            self._listener_thread.start()
            return self.tcp_port

    def stop(self):
        """Dừng listener và đóng các socket của dịch vụ."""
        with self._lock:
            listener = self._listener
            listener_thread = self._listener_thread
            sockets = list(self._sockets)
            self._listener = None
            self._listener_thread = None
            self._chats.clear()
            self._opening.clear()
            self._sockets.clear()

        if listener is not None:
            listener.close()
        for sock in sockets:
            self._close_socket(sock)
        if listener_thread is not None:
            listener_thread.join()

    def open_chat(self, peer_id):
        """Giữ kết nối hiện có hoặc mở TCP tới địa chỉ do discovery cung cấp."""
        with self._lock:
            if self._listener is None:
                self._failed("open_chat", peer_id, "TCP service is stopped")
                return
            if peer_id == self.peer_id:
                self._failed("open_chat", peer_id, "Cannot open chat with yourself")
                return
            if peer_id in self._chats or peer_id in self._opening:
                return

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            except OSError as error:
                self._failed("open_chat", peer_id, error)
                return

            self._opening[peer_id] = sock
            self._sockets.add(sock)
            local_peer = (self.peer_id, self.peer_name, self.tcp_port)

        try:
            peer = self._get_peer(peer_id)
            if peer is None:
                raise ValueError("Peer address is unavailable")

            address = (peer["ip"], peer["tcp_port"])
            _connect_and_exchange_hi(sock, address, local_peer, peer_id)
            chat = self._register_chat(peer_id, sock, outgoing=True)

            if chat is None:
                self._discard_socket(sock)
            else:
                Thread(target=self._read_chat, args=(peer_id, chat), daemon=True).start()
        except (OSError, EOFError, ValueError, KeyError) as error:
            with self._lock:
                if self._opening.get(peer_id) is sock and peer_id not in self._chats:
                    self._failed("open_chat", peer_id, error)
            self._discard_socket(sock)
        finally:
            with self._lock:
                if self._opening.get(peer_id) is sock:
                    del self._opening[peer_id]

    def send_message(self, peer_id, text):
        """Gửi một frame MSG qua kết nối đang dùng với peer."""
        chat = self._get_chat(peer_id)
        if chat is None:
            self._failed("send_message", peer_id, "Chat is not connected")
            return

        with chat.send_lock:
            if self._get_chat(peer_id) is not chat:
                self._failed("send_message", peer_id, "Chat connection changed")
                return
            try:
                send_chat_message(chat.sock, peer_id, text, self._bus)
            except ValueError as error:
                self._failed("send_message", peer_id, error)
            except OSError as error:
                self._failed("send_message", peer_id, error)
                self._disconnect(peer_id, chat, str(error))

    def leave_chat(self, peer_id):
        """Gửi BYE trước khi đóng kết nối chat."""
        with self._lock:
            chat = self._chats.get(peer_id)
            pending = self._opening.get(peer_id)
            if pending is not None and (chat is None or pending is not chat.sock):
                del self._opening[peer_id]
                self._sockets.discard(pending)
            else:
                pending = None

        if pending is not None:
            self._close_socket(pending)
        if chat is None:
            return

        with chat.send_lock:
            if self._get_chat(peer_id) is not chat:
                return
            try:
                send_packet(chat.sock, {"type": config.TYPE_BYE, "payload_size": 0})
            except OSError as error:
                self._failed("leave_chat", peer_id, error)
            finally:
                self._disconnect(peer_id, chat, "left_chat")

    # ------------------------------------------------------------------
    # Listener và xử lý từng kết nối
    # ------------------------------------------------------------------
    def _listen(self, listener):
        # Mỗi kết nối có luồng riêng, nên HI đến chậm không chặn accept().
        while True:
            try:
                sock, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            with self._lock:
                if self._listener is not listener:
                    sock.close()
                    return
                self._sockets.add(sock)
                local_peer = (self.peer_id, self.peer_name, self.tcp_port)

            Thread(
                target=self._accept_chat, args=(sock, local_peer), daemon=True
            ).start()

    def _accept_chat(self, sock, local_peer):
        peer_id = None
        try:
            greeting = recv_chat_hi(sock)
            peer_id = greeting["peer_id"]
            if peer_id == self.peer_id:
                raise ValueError("Cannot open chat with yourself")

            local_id, local_name, local_port = local_peer
            sock.settimeout(config.HI_FRAME_TIMEOUT)
            send_chat_hi(sock, local_id, local_name, local_port)
            sock.settimeout(None)
        except (OSError, EOFError, ValueError) as error:
            with self._lock:
                if sock in self._sockets:
                    self._failed("accept_chat", peer_id, error)
            self._discard_socket(sock)
            return

        chat = self._register_chat(peer_id, sock, outgoing=False)
        if chat is None:
            self._discard_socket(sock)
            return

        self._read_chat(peer_id, chat)

    def _register_chat(self, peer_id, sock, outgoing):
        chat = _ChatConnection(sock, outgoing)
        with self._lock:
            if sock not in self._sockets:
                return None

            old_chat = self._chats.get(peer_id)
            if old_chat is not None:
                # Cả hai đầu giữ kết nối do peer có ID nhỏ hơn khởi tạo.
                prefer_outgoing = self.peer_id < peer_id
                if old_chat.outgoing == prefer_outgoing or outgoing != prefer_outgoing:
                    return None

            self._chats[peer_id] = chat
            if old_chat is None:
                self._bus.publish("chat_connected", {"peer_id": peer_id})

        if old_chat is not None:
            self._discard_socket(old_chat.sock)
        return chat

    def _read_chat(self, peer_id, chat):
        reason = "connection_closed"
        try:
            while True:
                header = recv_header(chat.sock)
                if header["type"] == config.TYPE_BYE:
                    reason = "peer_left"
                    break

                if header["type"] != config.TYPE_MSG:
                    raise ValueError("Expected a MSG or BYE frame")

                text = header.get("text")
                _check_chat_text(text)
                with self._lock:
                    if self._chats.get(peer_id) is not chat:
                        break
                    self._bus.publish("message_received", {"peer_id": peer_id, "text": text})
        except EOFError:
            pass
        except (OSError, ValueError) as error:
            reason = str(error)
        finally:
            self._disconnect(peer_id, chat, reason)

    def _get_chat(self, peer_id):
        with self._lock:
            return self._chats.get(peer_id)

    def _disconnect(self, peer_id, chat, reason):
        with self._lock:
            # Một luồng của socket cũ chỉ được xóa đúng mục của nó.
            if self._chats.get(peer_id) is chat:
                del self._chats[peer_id]
                self._bus.publish("chat_disconnected", {"peer_id": peer_id, "reason": reason})
        self._discard_socket(chat.sock)

    def _discard_socket(self, sock):
        with self._lock:
            if sock not in self._sockets:
                return
            self._sockets.remove(sock)
        self._close_socket(sock)

    @staticmethod
    def _close_socket(sock):
        # shutdown() đánh thức luồng đang chờ đọc trên socket.
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    def _failed(self, operation, peer_id, error):
        self._bus.publish("operation_failed", {
            "operation": operation,
            "peer_id": peer_id,
            "reason": str(error),
        })
