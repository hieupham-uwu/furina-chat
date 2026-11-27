import socket
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import config
from core.event_bus import EventBus
from network import file_service
from network.protocol import encode_header, recv_exact, recv_header, send_packet
from network.tcp_service import TCPService


class TransferTests(unittest.TestCase):
    """Kiểm thử truyền file qua kết nối TCP purpose="media"."""

    def setUp(self):
        self.bus = EventBus()
        self.events = []

        # Mỗi test dùng thư mục downloads riêng, không đụng downloads/ thật.
        self.download_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.download_tmp.cleanup)
        self.download_dir = Path(self.download_tmp.name)
        download_patch = patch.object(file_service, "DOWNLOAD_DIR", self.download_dir)
        download_patch.start()
        self.addCleanup(download_patch.stop)

        self.source_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_tmp.cleanup)
        self.source_dir = Path(self.source_tmp.name)

        self.receiver_id = str(uuid.uuid4())
        self.sender_id = str(uuid.uuid4())
        self.addresses = {}

        self.tcp = TCPService(
            self.receiver_id, "Receiver", self.addresses.get, self.bus,
            host="127.0.0.1", port=0,
        )
        self.addCleanup(self.tcp.stop)
        port = self.tcp.start()
        self.addresses[self.receiver_id] = {"ip": "127.0.0.1", "tcp_port": port}

        file_service.configure(
            self.sender_id, "Sender", 50000, self.addresses.get, self.bus
        )
        self.addCleanup(file_service.stop)

    # ------------------------------------------------------------------
    # Tiện ích
    # ------------------------------------------------------------------
    def make_source(self, name, data):
        path = self.source_dir / name
        path.write_bytes(data)
        return path

    def wait_for_event(self, name, timeout=10, **fields):
        def matches(event):
            return event.name == name and all(
                event.payload.get(key) == value for key, value in fields.items()
            )

        for event in self.events:
            if matches(event):
                return event

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = self.bus.poll()
            if event is not None:
                self.events.append(event)
                if matches(event):
                    return event
            else:
                time.sleep(0.01)

        seen = [(event.name, event.payload) for event in self.events]
        self.fail(f"Không nhận được {name} {fields}; sự kiện đã thấy: {seen}")

    def drain(self, seconds=0.3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            event = self.bus.poll()
            if event is not None:
                self.events.append(event)
            else:
                time.sleep(0.01)

    def transfers(self, name, transfer_id):
        return [
            event for event in self.events
            if event.name == name and event.payload.get("transfer_id") == transfer_id
        ]

    # ------------------------------------------------------------------
    # Nhận/gửi file trọn vẹn
    # ------------------------------------------------------------------
    def test_regular_file_round_trip(self):
        data = bytes(range(256)) * 600  # 153 600 byte, hơn 2 chunk 64 KB
        source = self.make_source("bao-cao.bin", data)

        transfer_id = file_service.send_file(self.receiver_id, source)

        received = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        sent = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_SEND,
        )

        saved = Path(received.payload["local_path"])
        self.assertEqual(saved.read_bytes(), data)
        self.assertEqual(saved.parent, self.download_dir)
        self.assertEqual(sent.payload["total_bytes"], len(data))

        progress = self.transfers(config.EVENT_TRANSFER_PROGRESS, transfer_id)
        sent_progress = [
            event for event in progress
            if event.payload["direction"] == config.TRANSFER_DIRECTION_SEND
        ]
        self.assertGreaterEqual(len(sent_progress), 2)
        self.assertEqual(sent_progress[-1].payload["bytes_done"], len(data))

        # Kết nối media không được biến thành kết nối chat.
        self.drain()
        self.assertIsNone(self.tcp._get_chat(self.sender_id))
        self.assertFalse(any(event.name == "chat_connected" for event in self.events))
        self.assertFalse(any(event.name == "operation_failed" for event in self.events))

    def test_send_file_after_chat_peer_expires_from_discovery(self):
        sender = TCPService(
            self.sender_id, "Sender", self.addresses.get, self.bus,
            host="127.0.0.1", port=0,
        )
        self.addCleanup(sender.stop)
        port = sender.start()
        sender.open_chat(self.receiver_id)
        self.wait_for_event("chat_connected", peer_id=self.receiver_id)
        self.wait_for_event("chat_connected", peer_id=self.sender_id)

        self.addresses.clear()
        self.assertEqual(
            self.tcp.get_chat_peer(self.sender_id),
            {"ip": "127.0.0.1", "tcp_port": port},
        )
        file_service.configure(
            self.sender_id, "Sender", port, sender.get_chat_peer, self.bus,
        )

        data = b"File sent while discovery is unavailable"
        source = self.make_source("chat-fallback.txt", data)
        transfer_id = file_service.send_file(self.receiver_id, source)
        self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_SEND,
        )
        self.assertEqual((self.download_dir / source.name).read_bytes(), data)

        sender.leave_chat(self.receiver_id)
        self.assertIsNone(sender.get_chat_peer(self.receiver_id))

    def test_zero_byte_file(self):
        source = self.make_source("rong.txt", b"")

        transfer_id = file_service.send_file(self.receiver_id, source)

        received = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_SEND,
        )

        saved = Path(received.payload["local_path"])
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.stat().st_size, 0)

    def test_vietnamese_filename_and_duplicate_names(self):
        data = "Nội dung tiếng Việt".encode("utf-8")
        source = self.make_source("Tài liệu tiếng Việt.txt", data)

        for _ in range(2):
            transfer_id = file_service.send_file(self.receiver_id, source)
            self.wait_for_event(
                config.EVENT_TRANSFER_FINISHED,
                transfer_id=transfer_id,
                direction=config.TRANSFER_DIRECTION_RECEIVE,
            )
            self.wait_for_event(
                config.EVENT_TRANSFER_FINISHED,
                transfer_id=transfer_id,
                direction=config.TRANSFER_DIRECTION_SEND,
            )

        names = {path.name for path in self.download_dir.iterdir()}
        self.assertEqual(
            names,
            {"Tài liệu tiếng Việt.txt", "Tài liệu tiếng Việt (1).txt"},
        )
        for name in names:
            self.assertEqual((self.download_dir / name).read_bytes(), data)

    def test_two_transfers_at_the_same_time(self):
        first_data = b"a" * 10_000
        second_data = b"b" * 70_000
        first = self.make_source("thu-nhat.txt", first_data)
        second = self.make_source("thu-hai.txt", second_data)

        first_id = file_service.send_file(self.receiver_id, first)
        second_id = file_service.send_file(self.receiver_id, second)

        for transfer_id in (first_id, second_id):
            self.wait_for_event(
                config.EVENT_TRANSFER_FINISHED,
                transfer_id=transfer_id,
                direction=config.TRANSFER_DIRECTION_RECEIVE,
            )
            self.wait_for_event(
                config.EVENT_TRANSFER_FINISHED,
                transfer_id=transfer_id,
                direction=config.TRANSFER_DIRECTION_SEND,
            )

        self.assertEqual((self.download_dir / "thu-nhat.txt").read_bytes(), first_data)
        self.assertEqual((self.download_dir / "thu-hai.txt").read_bytes(), second_data)
        self.assertNotEqual(first_id, second_id)

    # ------------------------------------------------------------------
    # Độ tin cậy kết nối: cache địa chỉ và thử lại
    # ------------------------------------------------------------------
    def test_send_uses_cached_address_when_discovery_expires(self):
        data = b"noi dung da cache"
        source = self.make_source("cache.txt", data)

        first = file_service.send_file(self.receiver_id, source)
        self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=first,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=first,
            direction=config.TRANSFER_DIRECTION_SEND,
        )

        # Peer hết hạn discovery, nhưng địa chỉ đã được file_service ghi nhớ.
        del self.addresses[self.receiver_id]

        second = file_service.send_file(self.receiver_id, source)
        received = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=second,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        sent = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=second,
            direction=config.TRANSFER_DIRECTION_SEND,
        )

        self.assertEqual(sent.payload["total_bytes"], len(data))
        self.assertEqual(Path(received.payload["local_path"]).read_bytes(), data)

    def test_remember_peer_allows_send_after_discovery_expires(self):
        file_service.configure(
            self.sender_id, "Sender", 50000, lambda peer_id: None, self.bus
        )
        file_service.remember_peer(self.receiver_id, "127.0.0.1", self.tcp.tcp_port)

        source = self.make_source("remember.txt", b"da ghi nho")
        transfer_id = file_service.send_file(self.receiver_id, source)

        received = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        self.assertEqual(
            Path(received.payload["local_path"]).read_bytes(), b"da ghi nho"
        )

    def test_connect_retries_after_transient_failure(self):
        refused = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        refused.bind(("127.0.0.1", 0))
        refused_port = refused.getsockname()[1]
        refused.close()

        good = dict(self.addresses[self.receiver_id])
        calls = {"count": 0}

        def flaky_get(peer_id):
            if peer_id != self.receiver_id:
                return None
            calls["count"] += 1
            if calls["count"] == 1:
                return {"ip": "127.0.0.1", "tcp_port": refused_port}
            return good

        file_service.configure(self.sender_id, "Sender", 50000, flaky_get, self.bus)

        source = self.make_source("retry.txt", b"thu lai")
        transfer_id = file_service.send_file(self.receiver_id, source)

        sent = self.wait_for_event(
            config.EVENT_TRANSFER_FINISHED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_SEND,
        )
        self.assertGreaterEqual(calls["count"], 2)
        self.assertEqual(sent.payload["total_bytes"], len(b"thu lai"))

    # ------------------------------------------------------------------
    # Lỗi và ngắt kết nối
    # ------------------------------------------------------------------
    def test_closing_mid_transfer_removes_part_file(self):
        transfer_id = str(uuid.uuid4())
        raw = socket.create_connection(("127.0.0.1", self.tcp.tcp_port), timeout=5)
        try:
            send_packet(raw, {
                "type": config.TYPE_HI,
                "peer_id": str(uuid.uuid4()),
                "name": "RawSender",
                "tcp_port": 50001,
                "purpose": config.HI_PURPOSE_MEDIA,
                "payload_size": 0,
            })
            # Header khai báo 1000 byte nhưng chỉ gửi 100 byte rồi ngắt.
            raw.sendall(encode_header({
                "type": config.TYPE_FILE,
                "filename": "broken.bin",
                "transfer_id": transfer_id,
                "payload_size": 1_000,
            }))
            raw.sendall(b"x" * 100)
            raw.shutdown(socket.SHUT_WR)

            # Máy nhận sẽ gửi FILE_ERROR rồi đóng; đọc cho tới khi đóng.
            try:
                while raw.recv(4096):
                    pass
            except OSError:
                pass
        finally:
            raw.close()

        failed = self.wait_for_event(
            config.EVENT_TRANSFER_FAILED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_RECEIVE,
        )
        self.assertTrue(failed.payload["reason"])

        self.drain()
        part_files = [path for path in self.download_dir.iterdir()
                      if path.name.endswith(".part")]
        self.assertEqual(part_files, [])
        self.assertFalse((self.download_dir / "broken.bin").exists())
        self.assertEqual(
            self.transfers(config.EVENT_TRANSFER_FINISHED, transfer_id), []
        )

    def test_receive_completes_while_another_send_is_in_progress_and_cancelled(self):
        sending = threading.Event()
        resume = threading.Event()
        self.addCleanup(resume.set)
        publish_progress = file_service._publish_progress

        def pause_outgoing(details, done, last_update):
            stamp = publish_progress(details, done, last_update)
            if details["direction"] == config.TRANSFER_DIRECTION_SEND:
                sending.set()
                resume.wait(5)
            return stamp

        source = self.make_source("a-to-b.bin", b"a" * (config.FILE_CHUNK_SIZE * 4))
        with patch.object(file_service, "_publish_progress", pause_outgoing):
            outgoing = file_service.send_file(self.receiver_id, source)
            self.assertTrue(sending.wait(3))
            self.wait_for_event(
                config.EVENT_TRANSFER_STARTED, transfer_id=outgoing,
                direction=config.TRANSFER_DIRECTION_RECEIVE,
            )
            incoming = str(uuid.uuid4())
            data = b"C to A while A is sending" * 4000
            with socket.create_connection(("127.0.0.1", self.tcp.tcp_port), timeout=3) as sock:
                send_packet(sock, {
                    "type": config.TYPE_HI, "peer_id": str(uuid.uuid4()), "name": "C",
                    "tcp_port": 50001, "purpose": config.HI_PURPOSE_MEDIA, "payload_size": 0,
                })
                send_packet(sock, {
                    "type": config.TYPE_FILE, "filename": "c-to-a.bin",
                    "transfer_id": incoming, "payload_size": len(data),
                }, data)
                self.assertEqual(recv_header(sock)["type"], config.TYPE_FILE_OK)

            self.assertEqual((self.download_dir / "c-to-a.bin").read_bytes(), data)
            self.assertEqual(self.transfers(config.EVENT_TRANSFER_FINISHED, outgoing), [])
            self.assertTrue(file_service.cancel_send(outgoing))
            self.assertFalse(file_service.cancel_send(outgoing))
            resume.set()

            self.wait_for_event(config.EVENT_TRANSFER_CANCELLED, transfer_id=outgoing)
            self.wait_for_event(
                config.EVENT_TRANSFER_FAILED, transfer_id=outgoing,
                direction=config.TRANSFER_DIRECTION_RECEIVE,
            )

        self.assertTrue(source.exists())
        self.assertFalse((self.download_dir / source.name).exists())
        self.assertEqual(list(self.download_dir.glob("*.part")), [])

    def test_sender_reports_file_error_from_receiver(self):
        errors = []

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(5)
        port = listener.getsockname()[1]
        self.addCleanup(listener.close)

        def fake_receiver():
            try:
                connection, _ = listener.accept()
                with connection:
                    greeting = recv_header(connection)
                    assert greeting["purpose"] == config.HI_PURPOSE_MEDIA
                    file_header = recv_header(connection)
                    recv_exact(connection, file_header["payload_size"])
                    send_packet(connection, {
                        "type": config.TYPE_FILE_ERROR,
                        "transfer_id": file_header["transfer_id"],
                        "reason": "Ổ đĩa đầy",
                        "payload_size": 0,
                    })
            except Exception as error:  # noqa: BLE001 - chuyển lỗi về test
                errors.append(error)

        worker = threading.Thread(target=fake_receiver, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)

        self.addresses[self.receiver_id] = {"ip": "127.0.0.1", "tcp_port": port}
        source = self.make_source("loi.txt", b"noi dung")

        transfer_id = file_service.send_file(self.receiver_id, source)
        failed = self.wait_for_event(
            config.EVENT_TRANSFER_FAILED,
            transfer_id=transfer_id,
            direction=config.TRANSFER_DIRECTION_SEND,
        )

        self.assertEqual(errors, [])
        self.assertIn("Ổ đĩa đầy", failed.payload["reason"])
        self.assertEqual(
            self.transfers(config.EVENT_TRANSFER_FINISHED, transfer_id), []
        )


if __name__ == "__main__":
    unittest.main()
