import argparse
import os
import socket
import sys

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import config
from core.controller import Controller
from core.event_bus import EventBus
from core.state import AppState
from network import file_service
from network.tcp_service import TCPService
from network.udp_service import UDPService
from ui.main_window import MainWindow


def _resolve_display_name(cli_name: str | None) -> str:
    if cli_name and cli_name.strip():
        return cli_name.strip()
    env_name = (
        os.environ.get("FURINA_NAME")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or ""
    ).strip()
    if env_name:
        return env_name
    host = socket.gethostname().strip()
    return host if host else "Peer"


def main():
    parser = argparse.ArgumentParser(
        description="Furina Chat — P2P LAN Chat & File Sharing"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Tên hiển thị của bạn trên mạng LAN",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=getattr(config, "DEFAULT_TCP_PORT", 5000),
        help="Cổng TCP lắng nghe",
    )
    args = parser.parse_args()

    display_name = _resolve_display_name(args.name)
    bus = EventBus()
    app_state = AppState(my_name=display_name)

    with app_state.lock:
        app_state.my_tcp_port = args.port
        my_id = app_state.my_peer_id
        my_status = app_state.my_status

    app = MainWindow(
        event_bus=bus,
        state=app_state,
        my_name=display_name,
        my_status=my_status,
    )
    controller = Controller(app, app_state=app_state, event_bus=bus)
    app.set_controller(controller)

    udp_service = UDPService(
        peer_id=my_id,
        peer_name=display_name,
        tcp_port=args.port,
        event_bus=bus,
    )
    tcp_service = TCPService(
        peer_id=my_id,
        peer_name=display_name,
        get_peer=udp_service.get_peer,
        event_bus=bus,
        port=args.port,
    )

    actual_tcp_port = tcp_service.start()
    udp_service.tcp_port = actual_tcp_port
    with app_state.lock:
        app_state.my_tcp_port = actual_tcp_port

    file_service.configure(
        peer_id=my_id,
        peer_name=display_name,
        tcp_port=actual_tcp_port,
        get_peer=udp_service.get_peer,
        event_bus=bus,
    )
    udp_service.start()
    controller.bind_services(udp_service, tcp_service, file_service)

    app.mainloop()


if __name__ == "__main__":
    main()