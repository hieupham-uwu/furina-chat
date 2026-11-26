import os
import sys
import threading
import time
import customtkinter as ctk

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from core.controller import Controller
from core.state import state
from ui.chat_panel import ChatPanel
from ui.peer_sidebar import PeerSidebar


class MainWindow(ctk.CTk):
    def __init__(
        self,
        controller=None,
        event_bus=None,
        state=None,
        my_name: str = "Minh Anh",
        my_status: str = "online",
        enable_local_preview: bool = True,
    ):
        super().__init__()
        self.title("Furina Chat")
        self.geometry("1040x680")
        self.minsize(780, 520)
        self.configure(fg_color="#F5F3FF")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._poll_after_id = None
        self._closing = False

        try:
            self._windows_set_titlebar_color = lambda *_args, **_kwargs: None
        except Exception:
            pass

        self.state = state or globals()["state"]
        self.event_bus = event_bus
        self.enable_local_preview = enable_local_preview

        with self.state.lock:
            self.state.my_name = my_name
            self.state.my_status = my_status

        self.controller = controller or Controller(
            self, standalone_demo=self.enable_local_preview
        )

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = PeerSidebar(
            self,
            on_select_peer_cb=self._on_select_peer,
            on_change_status_cb=self._on_change_status,
            width=260,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(14, 12), pady=14)

        self.chat_panel = ChatPanel(self, controller=self.controller)
        self.chat_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)

        if self.enable_local_preview:
            self._seed_demo_data()
            threading.Thread(target=self._demo_incoming_loop, daemon=True).start()

        self._poll_after_id = self.after(100, self._poll_event_bus)

    def _on_select_peer(self, peer_id: str):
        if self.controller:
            self.controller.select_peer(peer_id)

    def _on_change_status(self, status: str):
        if self.controller:
            self.controller.change_status(status)

    def refresh_sidebar(self):
        with self.state.lock:
            peers = {k: dict(v) for k, v in self.state.peers.items()}
            unread = dict(self.state.unread_counts)
            active_id = self.state.active_peer_id

        self.sidebar.update_peers(peers, unread, active_id)

    def safe_update_status(self, peer_id: str, msg_id: str, status_text: str):
        if self._closing or not self.winfo_exists():
            return

        def _apply():
            if self._closing or not self.winfo_exists():
                return
            with self.state.lock:
                is_active = self.state.active_peer_id == peer_id
            if is_active:
                self.chat_panel.update_message_status(msg_id, status_text)

        try:
            self.after(0, _apply)
        except Exception:
            pass

    def safe_progress(self, peer_id: str, percent: float, text: str):
        if self._closing or not self.winfo_exists():
            return

        def _apply():
            if self._closing or not self.winfo_exists():
                return
            with self.state.lock:
                is_active = self.state.active_peer_id == peer_id
            if is_active:
                self.chat_panel.update_progress(percent, text)

        try:
            self.after(0, _apply)
        except Exception:
            pass

    def _poll_event_bus(self):
        if self._closing or not self.winfo_exists():
            return

        if self.event_bus is not None:
            for _ in range(100):
                event = None
                if hasattr(self.event_bus, "get_event"):
                    event = self.event_bus.get_event()
                elif hasattr(self.event_bus, "poll"):
                    ev_obj = self.event_bus.poll()
                    if ev_obj is not None:
                        event = {"type": ev_obj.name, "data": ev_obj.payload}
                if not event:
                    break
                if self.controller and hasattr(self.controller, "process_event"):
                    self.controller.process_event(event)

        if not self._closing and self.winfo_exists():
            self._poll_after_id = self.after(100, self._poll_event_bus)

    def _seed_demo_data(self):
        with self.state.lock:
            self.state.peers = {
                "p_hieu": {
                    "peer_id": "p_hieu",
                    "name": "Hiếu",
                    "ip": "192.168.1.10",
                    "tcp_port": 5001,
                    "status": "online",
                },
                "p_duong": {
                    "peer_id": "p_duong",
                    "name": "Dương (Offline)",
                    "ip": "192.168.1.11",
                    "tcp_port": 5002,
                    "status": "offline",
                },
            }
            self.state.active_peer_id = "p_hieu"
            self.state.chat_history["p_hieu"] = [
                {
                    "msg_id": "demo-init-1",
                    "sender_name": "Hệ thống",
                    "text": "Chào mừng Minh Anh!",
                    "type": "SYSTEM",
                    "timestamp": "",
                    "is_me": False,
                },
                {
                    "msg_id": "demo-init-2",
                    "sender_name": "Hiếu",
                    "text": "Thử gõ chữ vào ô Aa bên dưới rồi đợi vài giây xem tin đến có làm mất chữ không nhé.",
                    "type": "MSG",
                    "timestamp": "20:00",
                    "is_me": False,
                    "delivery_status": "Đã nhận",
                },
            ]
            history = list(self.state.chat_history["p_hieu"])
            peers = {k: dict(v) for k, v in self.state.peers.items()}
            unread = dict(self.state.unread_counts)
            active_id = self.state.active_peer_id

        self.sidebar.update_peers(peers, unread, active_id)
        self.chat_panel.render_messages(history)

    def _demo_incoming_loop(self):
        time.sleep(2.5)
        if self._closing:
            return
        incoming_online = {
            "msg_id": "demo-inc-1",
            "sender_name": "Hiếu",
            "text": "Tin nhắn mới tới — ô chữ bạn đang gõ vẫn giữ nguyên!",
            "type": "MSG",
            "timestamp": "20:01",
            "is_me": False,
            "delivery_status": "Đã nhận",
        }
        incoming_offline_peer = {
            "msg_id": "demo-inc-2",
            "sender_name": "Dương (Offline)",
            "text": "Dù hiển thị offline nhưng vẫn nhận tin nhắn bình thường!",
            "type": "MSG",
            "timestamp": "20:01",
            "is_me": False,
            "delivery_status": "Đã nhận",
        }

        def _push():
            if self._closing or not self.winfo_exists():
                return
            with self.state.lock:
                self.state.chat_history.setdefault("p_hieu", []).append(incoming_online)
                self.state.chat_history.setdefault("p_duong", []).append(
                    incoming_offline_peer
                )
                is_active_hieu = self.state.active_peer_id == "p_hieu"
                if self.state.active_peer_id != "p_duong":
                    self.state.unread_counts["p_duong"] = (
                        self.state.unread_counts.get("p_duong", 0) + 1
                    )
            if is_active_hieu:
                self.chat_panel.append_single_message(incoming_online)
            self.refresh_sidebar()

        try:
            self.after(0, _push)
        except Exception:
            pass

    def _on_close(self):
        self._closing = True
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None

        with self.state.lock:
            active_id = self.state.active_peer_id
            if active_id:
                self.state.drafts[active_id] = self.chat_panel.get_current_input()

        if self.controller and hasattr(self.controller, "shutdown"):
            try:
                self.controller.shutdown()
            except Exception:
                pass

        try:
            self.quit()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = MainWindow(enable_local_preview=True)
    app.mainloop()