"""Chạy Furina Chat trên mạng LAN.

Dùng giao diện: python main.py --gui --name Quan

Chế độ console dùng để kiểm tra UDP discovery và TCP chat.

Mở 2 terminal (cùng máy hoặc cùng LAN):
    python main.py --name Quan
    python main.py --name Minh

Gõ lệnh trong console:
    peers                   - liệt kê peer đã phát hiện
    connect <tên|peer_id>   - mở kết nối TCP tới peer
    msg <nội dung>          - gửi tin nhắn cho peer đang chat
    leave                   - đóng kết nối hiện tại
    online | away           - đổi trạng thái
    help                    - hiện trợ giúp
    quit                    - thoát

Mặc định TCP dùng cổng do hệ điều hành cấp (config.DEFAULT_TCP_PORT = 0)
và cổng thực tế được quảng bá trong HELLO.
"""

import argparse
import threading
import time
import uuid

import config
from core.event_bus import EventBus
from network.tcp_service import TCPService
from network.udp_service import UDPService


class ConsoleState:
    """Dữ liệu hiển thị dùng chung giữa luồng in sự kiện và luồng nhập lệnh."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.peers = {}
        self.active_peer = None
        self.connected = set()

    def name_of(self, peer_id):
        with self.lock:
            peer = self.peers.get(peer_id)
            return peer["name"] if peer else peer_id

    def peer_list(self):
        with self.lock:
            return list(self.peers.values())

    def get_active(self):
        with self.lock:
            return self.active_peer

    def set_active(self, peer_id):
        with self.lock:
            self.active_peer = peer_id
            self.connected.add(peer_id)

    def clear_active(self, peer_id):
        with self.lock:
            self.connected.discard(peer_id)
            if self.active_peer == peer_id:
                self.active_peer = None


def print_event(event, state):
    name, payload = event.name, event.payload

    if name == config.EVENT_PEER_UPDATED:
        with state.lock:
            state.peers[payload["peer_id"]] = payload
        print(
            f"[peer] {payload['name']} "
            f"{payload['ip']}:{payload['tcp_port']} ({payload['status']})"
        )
    elif name == config.EVENT_PEER_OFFLINE:
        with state.lock:
            peer = state.peers.pop(payload["peer_id"], None)
        label = peer["name"] if peer else payload["peer_id"]
        print(f"[peer] {label} đã offline")
    elif name == "chat_connected":
        peer_id = payload["peer_id"]
        state.set_active(peer_id)
        print(f"[tcp] đã kết nối với {state.name_of(peer_id)}")
    elif name == "chat_disconnected":
        peer_id = payload["peer_id"]
        state.clear_active(peer_id)
        print(
            f"[tcp] đã ngắt kết nối với {state.name_of(peer_id)} "
            f"({payload.get('reason', '')})"
        )
    elif name == "message_sent":
        print(f"[gửi] Bạn → {state.name_of(payload['peer_id'])}: {payload['text']}")
    elif name == "message_received":
        print(f"[nhận] {state.name_of(payload['peer_id'])}: {payload['text']}")
    elif name == "sticker_sent":
        print(
            f"[gửi sticker] → {state.name_of(payload['peer_id'])}: "
            f"{payload['pack']}/{payload['sticker_id']}"
        )
    elif name == "sticker_received":
        print(
            f"[nhận sticker] {state.name_of(payload['peer_id'])}: "
            f"{payload['pack']}/{payload['sticker_id']}"
        )
    elif name == "operation_failed":
        print(
            f"[lỗi] {payload['operation']} ({payload.get('peer_id')}): "
            f"{payload['reason']}"
        )


def printer_loop(bus, state, stop):
    while not stop.is_set():
        event = bus.poll()
        if event is None:
            time.sleep(0.05)
            continue
        print_event(event, state)


def print_help():
    print(
        "Lệnh:\n"
        "  peers                   - liệt kê peer đã phát hiện\n"
        "  connect <tên|peer_id>   - mở kết nối TCP tới peer\n"
        "  msg <nội dung>          - gửi tin nhắn cho peer đang chat\n"
        "  leave                   - đóng kết nối hiện tại\n"
        "  online / away           - đổi trạng thái\n"
        "  help                    - hiện trợ giúp\n"
        "  quit                    - thoát"
    )


def resolve_peer(state, target):
    peers = state.peer_list()
    if not peers:
        print("Chưa phát hiện peer nào.")
        return None
    if not target:
        return peers[0]["peer_id"]

    for peer in peers:
        if peer["peer_id"] == target:
            return target

    matches = [peer for peer in peers if peer["name"] == target]
    if len(matches) == 1:
        return matches[0]["peer_id"]
    if not matches:
        print(f"Không tìm thấy peer '{target}'. Gõ 'peers' để xem.")
        return None

    ids = ", ".join(peer["peer_id"] for peer in matches)
    print(f"Có nhiều peer tên '{target}', dùng peer_id: {ids}")
    return None


def run_gui(name, port):
    from tkinter import messagebox

    from core.state import AppState
    from network import file_service
    from ui.main_window import MainWindow

    state = AppState()
    bus = EventBus()
    window = MainWindow(
        state=state, event_bus=bus, my_name=name, enable_local_preview=False
    )
    udp = None

    def get_peer(peer_id):
        return udp.get_peer(peer_id) if udp is not None else None

    tcp = TCPService(state.my_peer_id, name, get_peer, bus, port=port)
    window.controller.bind_services(None, tcp, None)
    try:
        try:
            state.my_tcp_port = tcp.start()
            udp = UDPService(state.my_peer_id, name, state.my_tcp_port, bus)
            window.controller.bind_services(udp, tcp, file_service)
            file_service.configure(
                state.my_peer_id, name, state.my_tcp_port, get_peer, bus
            )
            udp.start()
        except OSError as error:
            messagebox.showerror(
                "Furina Chat",
                f"Không khởi động được mạng LAN.\n{error}",
                parent=window,
            )
            return 1

        window.mainloop()
    finally:
        window._on_close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Furina Chat trên mạng LAN")
    parser.add_argument("--gui", action="store_true", help="mở giao diện chat LAN")
    parser.add_argument(
        "--name",
        default=f"User-{uuid.uuid4().hex[:4]}",
        help="tên hiển thị của bạn",
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=config.DEFAULT_TCP_PORT,
        help="cổng TCP (0 = hệ điều hành tự cấp)",
    )
    args = parser.parse_args()
    args.name = args.name.strip()
    if not args.name:
        parser.error("--name không được để trống")
    if not 0 <= args.tcp_port <= 65535:
        parser.error("--tcp-port phải nằm trong khoảng 0 đến 65535")
    if args.gui:
        return run_gui(args.name, args.tcp_port)

    # peer_id tạo một lần, dùng chung cho HELLO (UDP) và HI (TCP)
    peer_id = str(uuid.uuid4())
    bus = EventBus()
    state = ConsoleState()

    udp = None

    def get_peer(pid):
        return udp.get_peer(pid) if udp is not None else None

    tcp = TCPService(peer_id, args.name, get_peer, bus, port=args.tcp_port)
    try:
        tcp_port = tcp.start()
    except OSError as error:
        print(f"Không mở được TCP: {error}")
        return 1

    udp = UDPService(peer_id, args.name, tcp_port, bus)
    try:
        udp.start()
    except OSError as error:
        print(f"Không mở được UDP discovery: {error}")
        tcp.stop()
        return 1

    print("=== Furina Chat - test UDP + TCP ===")
    print(f"Tên       : {args.name}")
    print(f"peer_id   : {peer_id}")
    print(f"TCP       : {config.DEFAULT_TCP_HOST}:{tcp_port}")
    print(f"Discovery : {config.UDP_BROADCAST_ADDR}")
    print()

    printer_stop = threading.Event()
    printer = threading.Thread(
        target=printer_loop, args=(bus, state, printer_stop), daemon=True
    )
    printer.start()
    print("Đang chạy. Gõ 'help' để xem lệnh.\n")

    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue

            command, _, argument = line.partition(" ")
            command = command.lower()
            argument = argument.strip()

            if command in ("quit", "exit", "q"):
                break
            if command == "peers":
                peers = state.peer_list()
                if not peers:
                    print("(chưa phát hiện peer nào)")
                for peer in peers:
                    print(
                        f"  {peer['name']:<12} "
                        f"{peer['ip']}:{peer['tcp_port']}  "
                        f"{peer['status']}  id={peer['peer_id']}"
                    )
            elif command == "connect":
                target = resolve_peer(state, argument)
                if target is not None:
                    print(f"Đang kết nối tới {state.name_of(target)}...")
                    tcp.open_chat(target)
            elif command == "msg":
                active = state.get_active()
                if active is None:
                    print("Chưa kết nối peer nào. Dùng 'connect <tên>' trước.")
                elif not argument:
                    print("Cú pháp: msg <nội dung>")
                else:
                    tcp.send_message(active, argument)
            elif command == "leave":
                active = state.get_active()
                if active is None:
                    print("Không có kết nối nào để đóng.")
                else:
                    tcp.leave_chat(active)
            elif command in config.VALID_STATUSES:
                udp.set_status(command)
                print(f"Đã đổi trạng thái: {command}")
            elif command in ("help", "h"):
                print_help()
            else:
                print("Lệnh không hợp lệ. Gõ 'help' để xem trợ giúp.")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        printer_stop.set()
        udp.stop()
        tcp.stop()
        printer.join(timeout=2)
        print("Đã dừng.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
