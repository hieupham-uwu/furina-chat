import time
import unittest
from unittest.mock import patch

import config
from core.event_bus import EventBus
from network.udp_service import UDPService


class DiscoveryTests(unittest.TestCase):
    def test_unicast_reply_makes_discovery_mutual(self):
        left_bus = EventBus()
        right_bus = EventBus()
        with patch.object(config, "UDP_DISCOVERY_PORT", 0):
            left = UDPService("left", "Left", 5001, left_bus, discovery_ip="127.0.0.1")
            right = UDPService("right", "Right", 5002, right_bus, discovery_ip="127.0.0.1")
            self.addCleanup(left.stop)
            self.addCleanup(right.stop)
            left.start()
            right.start()

            # Chỉ Left tìm được đường tới Right trong lượt đầu.
            left._send_hello(("127.0.0.1", right._sock.getsockname()[1]))
            left_event = right_event = None
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                left_event = left_event or left_bus.poll()
                right_event = right_event or right_bus.poll()
                if left_event and right_event:
                    break
                time.sleep(0.01)

            self.assertEqual(left.get_peer("right")["tcp_port"], 5002)
            self.assertEqual(right.get_peer("left")["tcp_port"], 5001)
            self.assertEqual(left_event.payload["ip"], "127.0.0.1")
            self.assertEqual(right_event.payload["ip"], "127.0.0.1")
