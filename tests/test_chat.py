import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from core.event_bus import EventBus
from network import tcp_service
from network.tcp_service import TCPService


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.addresses = {}
        self.duong, self.duong_bus = self.start_peer(1, "Dương")
        self.hieu, self.hieu_bus = self.start_peer(2, "Hiếu")

    def start_peer(self, number, name):
        peer_id = f"00000000-0000-0000-0000-{number:012d}"
        bus = EventBus()
        service = TCPService(peer_id, name, self.addresses.get, bus, host="127.0.0.1")
        self.addCleanup(service.stop)
        port = service.start()
        self.addresses[peer_id] = {"ip": "127.0.0.1", "tcp_port": port}
        return service, bus

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
        self.wait_for_event(self.hieu_bus, "chat_connected", self.duong.peer_id)
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


if __name__ == "__main__":
    unittest.main()
