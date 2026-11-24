import socket
import time
from threading import Thread
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


def open_chat(address, local_peer, expected_peer_id, bus):
    local_id, local_name, local_port = local_peer
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.settimeout(config.HI_FRAME_TIMEOUT)
        sock.connect(address)

        send_chat_hi(sock, local_id, local_name, local_port)
        reply = recv_chat_hi(sock)

        if reply["peer_id"] != expected_peer_id:
            raise ValueError("The peer ID in HI does not match")

        sock.settimeout(None)
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