import socket
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event
from unittest.mock import patch

import config
from core.event_bus import EventBus
from network import tcp_service
from network.protocol import recv_exact, recv_header, send_packet
from network.tcp_service import TCPService


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.addresses = {}
        self.duong, self.duong_bus = self.start_peer(1, "Dương")
        self.hieu, self.hieu_bus = self.start_peer(2, "Hiếu")

    def start_peer(self, number, name, *, on_media=None):
        peer_id = f"00000000-0000-0000-0000-{number:012d}"
        bus = EventBus()
        service = TCPService(
            peer_id, name, self.addresses.get, bus, host="127.0.0.1", on_media=on_media,
        )
        self.addCleanup(service.stop)
        port = service.start()
        self.addresses[peer_id] = {"ip": "127.0.0.1", "tcp_port": port}
        return service, bus

    def connect_for_media(self, receiver, *, purpose="media"):
        sock = socket.create_connection(("127.0.0.1", receiver.tcp_port), timeout=3)
        self.addCleanup(sock.close)
        send_packet(sock, {
            "type": config.TYPE_HI,
            "peer_id": self.duong.peer_id,
            "name": self.duong.peer_name,
            "tcp_port": self.duong.tcp_port,
            "purpose": purpose,
            "payload_size": 0,
        })
        return sock

    def wait_for(self, condition):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = condition()
            if result:
                return result
            time.sleep(0.01)
        self.fail("Timed out waiting for the chat test condition")

    def wait_for_event(self, bus, name, peer_id):
        def matching_event():
            event = bus.poll()
            while event is not None:
                if event.name == "operation_failed":
                    self.fail(str(event.payload))
                if event.name == name and event.payload["peer_id"] == peer_id:
                    return event
                event = bus.poll()
            return None

        return self.wait_for(matching_event)

    def test_reuses_chat_and_keeps_two_peers_with_the_same_name(self):
        other_hieu, other_bus = self.start_peer(3, "Hiếu")

        self.duong.open_chat(self.hieu.peer_id)
        self.duong.open_chat(other_hieu.peer_id)
        incoming = self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)
        self.assertEqual(incoming.payload, {
            "peer_id": self.duong.peer_id,
            "name": self.duong.peer_name,
            "ip": "127.0.0.1",
            "tcp_port": self.duong.tcp_port,
        })
        self.wait_for_event(other_bus, "chat_connected", self.duong.peer_id)

        self.wait_for_event(self.duong_bus, "chat_connected", self.hieu.peer_id)
        self.wait_for_event(self.duong_bus, "chat_connected", other_hieu.peer_id)
        first_chat = self.duong._get_chat(self.hieu.peer_id)
        del self.addresses[self.hieu.peer_id]
        self.duong.open_chat(self.hieu.peer_id)
        self.assertIs(self.duong._get_chat(self.hieu.peer_id), first_chat)
        self.assertIsNone(self.duong_bus.poll())

        self.duong.send_message(self.hieu.peer_id, "Chào Hiếu!")
        self.duong.send_message(self.hieu.peer_id, "Tin thứ hai")
        self.duong.send_message(other_hieu.peer_id, "Tin cho Hiếu còn lại")

        for text in ("Chào Hiếu!", "Tin thứ hai"):
            event = self.wait_for_event(self.hieu_bus, "message_received", self.duong.peer_id)
            self.assertEqual(event.payload["text"], text)
        event = self.wait_for_event(other_bus, "message_received", self.duong.peer_id)
        self.assertEqual(event.payload["text"], "Tin cho Hiếu còn lại")

    def test_simultaneous_open_keeps_connection_from_smaller_peer_id(self):
        both_opening = Barrier(2)
        allow_preferred = Event()
        connect = tcp_service._connect_and_exchange_hi

        def wait_then_connect(sock, address, local_peer, expected_peer_id):
            both_opening.wait(timeout=3)
            if local_peer[0] == self.duong.peer_id and not allow_preferred.wait(3):
                raise TimeoutError("The first connection did not get registered")
            connect(sock, address, local_peer, expected_peer_id)

        with patch.object(tcp_service, "_connect_and_exchange_hi", wait_then_connect):
            with ThreadPoolExecutor(max_workers=2) as executor:
                preferred = executor.submit(self.duong.open_chat, self.hieu.peer_id)
                other = executor.submit(self.hieu.open_chat, self.duong.peer_id)
                try:
                    other.result(timeout=3)
                    self.wait_for_event(self.duong_bus, "chat_connected", self.hieu.peer_id)
                    old_chat = self.duong._get_chat(self.hieu.peer_id)
                    self.assertFalse(old_chat.outgoing)
                finally:
                    allow_preferred.set()
                preferred.result(timeout=3)

        def preferred_registered():
            duong_chat = self.duong._get_chat(self.hieu.peer_id)
            hieu_chat = self.hieu._get_chat(self.duong.peer_id)
            return duong_chat and hieu_chat and duong_chat.outgoing and not hieu_chat.outgoing

        self.wait_for(preferred_registered)
        self.wait_for(lambda: old_chat.sock.fileno() == -1)
        self.duong.send_message(self.hieu.peer_id, "Đường kết nối của Dương")
        self.hieu.send_message(self.duong.peer_id, "Hiếu dùng lại kết nối đó")
        self.assertEqual(
            self.wait_for_event(self.hieu_bus, "message_received", self.duong.peer_id).payload["text"],
            "Đường kết nối của Dương",
        )
        self.assertEqual(
            self.wait_for_event(self.duong_bus, "message_received", self.hieu.peer_id).payload["text"],
            "Hiếu dùng lại kết nối đó",
        )

    def test_sticker_and_messages_share_chat_in_order(self):
        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.duong_bus, "chat_connected", self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)

        self.duong.send_message(self.hieu.peer_id, "Chào Hiếu!")
        self.duong.send_sticker(self.hieu.peer_id, "columbina", "id_1")
        self.duong.send_message(self.hieu.peer_id, "Tin tiếp theo")

        sticker = {"pack": "columbina", "sticker_id": "id_1"}
        received = [self.wait_for(self.hieu_bus.poll) for _ in range(3)]
        self.assertEqual(
            [(event.name, event.payload) for event in received],
            [
                ("message_received", {"peer_id": self.duong.peer_id, "text": "Chào Hiếu!"}),
                ("sticker_received", {"peer_id": self.duong.peer_id, **sticker}),
                ("message_received", {"peer_id": self.duong.peer_id, "text": "Tin tiếp theo"}),
            ],
        )
        sent = self.wait_for_event(self.duong_bus, "sticker_sent", self.hieu.peer_id)
        self.assertEqual(sent.payload, {"peer_id": self.hieu.peer_id, **sticker})

        self.hieu.send_sticker(self.duong.peer_id, "other_pack", "id_42")
        reply = self.wait_for_event(self.duong_bus, "sticker_received", self.hieu.peer_id)
        self.assertEqual(reply.payload, {
            "peer_id": self.hieu.peer_id, "pack": "other_pack", "sticker_id": "id_42",
        })

    def test_invalid_sticker_to_send_keeps_chat_open(self):
        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.duong_bus, "chat_connected", self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)

        for pack, sticker_id in (("", "id_1"), ("columbina", "../id_1"), ("columbina", 1)):
            with self.subTest(pack=pack, sticker_id=sticker_id):
                self.duong.send_sticker(self.hieu.peer_id, pack, sticker_id)
                failure = self.wait_for(self.duong_bus.poll)
                self.assertEqual(failure.name, "operation_failed")
                self.assertEqual(failure.payload["operation"], "send_sticker")
                self.assertEqual(failure.payload["peer_id"], self.hieu.peer_id)

        self.duong.send_message(self.hieu.peer_id, "Chat vẫn hoạt động")
        received = self.wait_for(self.hieu_bus.poll)
        self.assertEqual(received.name, "message_received")
        self.assertEqual(received.payload["text"], "Chat vẫn hoạt động")

    def test_invalid_received_sticker_closes_chat_without_sticker_event(self):
        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)

        chat = self.duong._get_chat(self.hieu.peer_id)
        send_packet(chat.sock, {
            "type": config.TYPE_STICKER,
            "payload_size": 0,
            "pack": "columbina",
        })

        event = self.wait_for(self.hieu_bus.poll)
        self.assertEqual(event.name, "chat_disconnected")
        self.assertEqual(event.payload["peer_id"], self.duong.peer_id)
        self.assertEqual(event.payload["reason"], "Invalid sticker sticker_id")

    def test_leave_reopen_and_handle_remote_close(self):
        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)

        self.duong.leave_chat(self.hieu.peer_id)
        left = self.wait_for_event(self.duong_bus, "chat_disconnected", self.hieu.peer_id)
        received_bye = self.wait_for_event(self.hieu_bus, "chat_disconnected", self.duong.peer_id)
        self.assertEqual(left.payload["reason"], "left_chat")
        self.assertEqual(received_bye.payload["reason"], "peer_left")
        self.assertIsNone(self.duong._get_chat(self.hieu.peer_id))
        self.assertIsNone(self.hieu._get_chat(self.duong.peer_id))

        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)
        self.duong.send_message(self.hieu.peer_id, "Mở chat lại")
        event = self.wait_for_event(self.hieu_bus, "message_received", self.duong.peer_id)
        self.assertEqual(event.payload["text"], "Mở chat lại")

        self.hieu.stop()
        self.wait_for_event(self.duong_bus, "chat_disconnected", self.hieu.peer_id)
        self.assertIsNone(self.duong._get_chat(self.hieu.peer_id))


    def test_media_handoff_leaves_chat_available(self):
        media_started = Event()
        received_media = Queue()
        transfer_id = "550e8400-e29b-41d4-a716-446655440000"

        def handle_incoming(sock, peer_id):
            with sock:
                media_started.set()
                header = recv_header(sock)
                payload = recv_exact(sock, header["payload_size"])
                received_media.put((peer_id, header, payload))
                send_packet(sock, {
                    "type": config.TYPE_FILE_OK,
                    "transfer_id": header["transfer_id"],
                    "payload_size": 0,
                })

        receiver, receiver_bus = self.start_peer(3, "Mai", on_media=handle_incoming)
        self.duong.open_chat(receiver.peer_id)
        self.wait_for_event(receiver_bus, "chat_connected", self.duong.peer_id)

        media = self.connect_for_media(receiver)
        self.assertTrue(media_started.wait(3))
        self.duong.send_message(receiver.peer_id, "Chat trong khi chờ dữ liệu tệp")
        event = self.wait_for(receiver_bus.poll)
        self.assertEqual(event.name, "message_received")
        self.assertEqual(event.payload["text"], "Chat trong khi chờ dữ liệu tệp")

        header = {
            "type": config.TYPE_FILE,
            "transfer_id": transfer_id,
            "filename": "note.txt",
            "payload_size": 3,
        }
        send_packet(media, header, b"ABC")
        self.assertEqual(recv_header(media), {
            "type": config.TYPE_FILE_OK,
            "transfer_id": transfer_id,
            "payload_size": 0,
        })
        self.assertEqual(received_media.get(timeout=3), (self.duong.peer_id, header, b"ABC"))

    def test_media_without_handler_closes_only_media_connection(self):
        media = self.connect_for_media(self.hieu)
        event = self.wait_for(self.hieu_bus.poll)
        self.assertEqual(event.name, "operation_failed")
        self.assertEqual(event.payload, {
            "operation": "accept_media",
            "peer_id": self.duong.peer_id,
            "reason": "No media handler is configured",
        })
        self.assertEqual(media.recv(1), b"")

        self.duong.open_chat(self.hieu.peer_id)
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)

    def test_invalid_hi_purpose_does_not_reach_media_handler(self):
        handler_called = Event()

        def handle_incoming(sock, peer_id):
            with sock:
                handler_called.set()

        receiver, receiver_bus = self.start_peer(3, "Mai", on_media=handle_incoming)
        sock = self.connect_for_media(receiver, purpose="unknown")
        event = self.wait_for(receiver_bus.poll)
        self.assertEqual(event.name, "operation_failed")
        self.assertEqual(event.payload["reason"], "Expected a chat or media HI frame")
        self.assertEqual(sock.recv(1), b"")
        self.assertFalse(handler_called.is_set())

    def test_media_handler_failure_closes_socket(self):
        def handle_incoming(sock, peer_id):
            raise RuntimeError("File handler stopped")

        receiver, receiver_bus = self.start_peer(3, "Mai", on_media=handle_incoming)
        media = self.connect_for_media(receiver)
        event = self.wait_for(receiver_bus.poll)
        self.assertEqual(event.name, "operation_failed")
        self.assertEqual(event.payload, {
            "operation": "handle_media",
            "peer_id": self.duong.peer_id,
            "reason": "File handler stopped",
        })
        self.assertEqual(media.recv(1), b"")

    def test_stop_leaves_handed_off_socket_with_media_handler(self):
        media_sockets = Queue()

        def handle_incoming(sock, peer_id):
            media_sockets.put(sock)

        receiver, receiver_bus = self.start_peer(3, "Mai", on_media=handle_incoming)
        media = self.connect_for_media(receiver)
        accepted = media_sockets.get(timeout=3)
        self.addCleanup(accepted.close)

        receiver.stop()
        accepted.settimeout(3)
        media.sendall(b"A")
        self.assertEqual(recv_exact(accepted, 1), b"A")

        port = receiver.start()
        self.addresses[receiver.peer_id] = {"ip": "127.0.0.1", "tcp_port": port}
        self.duong.open_chat(receiver.peer_id)
        self.wait_for_event(receiver_bus, "chat_connected", self.duong.peer_id)


if __name__ == "__main__":
    unittest.main()
