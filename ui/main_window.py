import gc
import os
import sys
import time
import customtkinter as ctk

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import config
from core.controller import Controller
from core.state import AppState
from ui.chat_panel import ChatPanel
from ui.peer_sidebar import PeerSidebar
from ui.sticker_picker import StickerPicker


class MainWindow(ctk.CTk):
    def __init__(
        self,
        controller=None,
        event_bus=None,
        state=None,
        my_name: str | None = None,
        my_status: str = getattr(config, "STATUS_ONLINE", "online"),
    ):
        super().__init__()
        self.geometry("1040x680")
        self.minsize(780, 520)
        self.configure(fg_color="#F5F3FF")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._poll_after_id = None
        self._next_ui_collection = None
        self._closing = False
        self._picker_win = None

        try:
            self._windows_set_titlebar_color = lambda *_args, **_kwargs: None
        except Exception:
            pass

        self.app_state = state or AppState(my_name=my_name)
        self.event_bus = event_bus

        norm_status = "away" if (my_status or "").lower() == "away" else "online"
        with self.app_state.lock:
            if my_name and my_name.strip():
                self.app_state.my_name = my_name.strip()
            self.app_state.my_status = norm_status
            current_name = self.app_state.my_name

        self.title(f"Furina Chat — {current_name}")

        self.controller = controller or Controller(
            self, app_state=self.app_state, event_bus=self.event_bus
        )

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = PeerSidebar(
            self,
            on_select_peer_cb=self._on_select_peer,
            on_change_name_cb=self._on_change_name,
            on_toggle_activity_cb=self._on_toggle_activity,
            width=275,
        )
        self.sidebar.set_my_name(current_name)
        self.sidebar.set_my_status(norm_status)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(14, 12), pady=14)

        self.chat_panel = ChatPanel(
            self,
            controller=self.controller,
            on_toggle_sticker_cb=self._on_toggle_sticker_popup,
        )
        self.chat_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)

        self.bind_all("<KeyPress>", self._on_user_input_event, add="+")

        self._poll_after_id = self.after(50, self._poll_event_bus)

    def mainloop(self, n=0):
        if not gc.isenabled():
            return super().mainloop(n)

        # Tk image finalizers must run on the UI thread, even for widget cycles.
        gc.disable()
        self._next_ui_collection = time.monotonic() + 2
        try:
            return super().mainloop(n)
        finally:
            self._next_ui_collection = None
            gc.collect()
            gc.enable()

    def _on_user_input_event(self, _event):
        if self.controller:
            self.controller.record_user_activity(auto_back_online=True)

    def _on_toggle_sticker_popup(self, anchor_widget=None):
        if self._picker_win is not None and self._picker_win.winfo_exists():
            try:
                self._picker_win.destroy()
            except Exception:
                pass
            self._picker_win = None
            return

        target = anchor_widget or getattr(self.chat_panel, "btn_sticker", None)
        self._picker_win = StickerPicker(
            self,
            on_sticker_selected=self._on_sticker_chosen,
            anchor_widget=target,
        )

    def hide_sticker_popup(self):
        if self._picker_win is not None and self._picker_win.winfo_exists():
            try:
                self._picker_win.destroy()
            except Exception:
                pass
        self._picker_win = None

    def _on_sticker_chosen(self, pack: str, sticker_id: str):
        self._picker_win = None
        if self.controller and self.controller.has_active_peer():
            self.chat_panel.hide_error()
            self.chat_panel.entry_msg.focus_set()
            self.controller.send_sticker(pack, sticker_id)
        else:
            self.chat_panel.show_error(
                "Cảnh báo: Hãy chọn một người ở danh sách bên trái để gửi sticker."
            )

    def set_controller(self, controller):
        self.controller = controller
        self.chat_panel.controller = controller

    def _on_select_peer(self, peer_id: str):
        if self.controller:
            self.controller.select_peer(peer_id)

    def _on_change_name(self, new_name: str):
        if self.controller:
            self.controller.change_my_name(new_name)

    def _on_toggle_activity(self, new_status: str):
        if self.controller:
            self.controller.set_activity_status(new_status)

    def refresh_sidebar(self):
        with self.app_state.lock:
            peers = {str(k): dict(v) for k, v in self.app_state.peers.items()}
            unread = {str(k): v for k, v in self.app_state.unread_counts.items()}
            last_act = {str(k): v for k, v in self.app_state.last_activity.items()}
            connected_ids = {
                str(pid)
                for pid, msgs in self.app_state.chat_history.items()
                if len(msgs) > 0
            }
            active_id = (
                str(self.app_state.active_peer_id) if self.app_state.active_peer_id else None
            )

        self.sidebar.update_peers(
            peers,
            unread,
            active_id,
            last_activity=last_act,
            connected_ids=connected_ids,
        )

    def safe_update_status(self, peer_id: str, msg_id: str, status_text: str):
        if self._closing or not self.winfo_exists():
            return

        def _apply():
            if self._closing or not self.winfo_exists():
                return
            with self.app_state.lock:
                is_active = self.app_state.active_peer_id == str(peer_id)
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
            with self.app_state.lock:
                is_active = self.app_state.active_peer_id == str(peer_id)
            if is_active:
                self.chat_panel.update_progress(percent, text)

        try:
            self.after(0, _apply)
        except Exception:
            pass

    def _next_bus_event(self):
        bus = self.event_bus
        if bus is None:
            return None
        if hasattr(bus, "poll") and callable(bus.poll):
            return bus.poll()
        if hasattr(bus, "get_event") and callable(bus.get_event):
            return bus.get_event()
        return None

    def _poll_event_bus(self):
        if self._closing or not self.winfo_exists():
            return

        if self._next_ui_collection is not None and time.monotonic() >= self._next_ui_collection:
            gc.collect()
            self._next_ui_collection = time.monotonic() + 2

        if self.controller:
            self.controller.check_idle_away()

        for _ in range(100):
            ev = self._next_bus_event()
            if ev is None:
                break
            if self.controller and hasattr(self.controller, "process_event"):
                self.controller.process_event(ev)

        if not self._closing and self.winfo_exists():
            self._poll_after_id = self.after(50, self._poll_event_bus)

    def _on_close(self):
        self._closing = True
        self.hide_sticker_popup()
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None

        if self.controller:
            try:
                self.controller.shutdown()
            except Exception:
                pass

        try:
            self.quit()
        except Exception:
            pass
        self.destroy()
