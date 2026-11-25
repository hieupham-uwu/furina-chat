import socket
import struct
import unittest
from unittest.mock import Mock

import config
from network.protocol import (
    encode_header,
    pack_udp_hello,
    recv_exact,
    recv_header,
    send_packet,
    unpack_udp_hello,
)

MSG = {"type": "MSG", "text": "Chào 👋", "payload_size": 0}


class ProtocolTests(unittest.TestCase):
    def test_recv_exact_collects_partial_reads(self):
        sock = Mock()
        sock.recv.side_effect = [b"ab", b"cde"]

        self.assertEqual(recv_exact(sock, 5), b"abcde")
        self.assertEqual([call.args[0] for call in sock.recv.call_args_list], [5, 3])

    def test_recv_exact_reports_early_eof(self):
        sock = Mock()
        sock.recv.side_effect = [b"ab", b""]
        with self.assertRaises(EOFError):
            recv_exact(sock, 5)

    def test_prefix_contains_utf8_byte_count(self):
        frame = encode_header(MSG)
        self.assertEqual(frame[:6], b"Furina")
        self.assertEqual(frame[6:10], bytes.fromhex("00 00 00 38"))
        self.assertEqual(len(frame), 66)

    def test_file_payload_then_message(self):
        file_header = {
            "type": "FILE",
            "filename": "note.txt",
            "transfer_id": "550e8400-e29b-41d4-a716-446655440000",
            "payload_size": 3,
        }
        sender, receiver = socket.socketpair()
        with sender, receiver:
            receiver.settimeout(2)
            send_packet(sender, file_header, b"ABC")
            send_packet(sender, MSG)

            header = recv_header(receiver)
            self.assertEqual(header, file_header)
            self.assertEqual(recv_exact(receiver, header["payload_size"]), b"ABC")
            self.assertEqual(recv_header(receiver), MSG)

    def test_rejects_invalid_magic_and_lengths(self):
        for parts in (
            [b"wrong!"],
            [config.MAGIC_BYTES, struct.pack("!I", 0)],
            [config.MAGIC_BYTES, struct.pack("!I", config.MAX_JSON_HEADER_SIZE + 1)],
        ):
            with self.subTest(parts=parts):
                sock = Mock()
                sock.recv.side_effect = parts
                with self.assertRaises(ValueError):
                    recv_header(sock)
                self.assertEqual(sock.recv.call_count, len(parts))

    def test_rejects_invalid_json_and_header_fields(self):
        for raw in (
            b"\xff",
            b"{",
            b"[]",
            b'{"type":"OTHER","payload_size":0}',
            b'{"type":"MSG","payload_size":true}',
            b'{"type":"BYE","payload_size":1}',
            b'{"type":"MSG","payload_size":0,"extra":NaN}',
        ):
            with self.subTest(raw=raw):
                sock = Mock()
                sock.recv.side_effect = [
                    config.MAGIC_BYTES,
                    struct.pack("!I", len(raw)),
                    raw,
                ]
                with self.assertRaises(ValueError):
                    recv_header(sock)

    def test_send_rejects_incorrect_payload_size_before_writing(self):
        sock = Mock()
        with self.assertRaises(ValueError):
            send_packet(sock, MSG, b"x")
        sock.sendall.assert_not_called()

    def test_recv_header_reports_truncated_json(self):
        sock = Mock()
        sock.recv.side_effect = [config.MAGIC_BYTES, struct.pack("!I", 2), b"{", b""]
        with self.assertRaises(EOFError):
            recv_header(sock)

    def test_udp_hello_still_round_trips(self):
        peer_id = "550e8400-e29b-41d4-a716-446655440000"
        packed = pack_udp_hello(peer_id, "Dương", 5000, "online")
        self.assertEqual(unpack_udp_hello(packed)["name"], "Dương")
        self.assertIsNone(unpack_udp_hello(b"invalid"))