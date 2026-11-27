from collections import deque

import customtkinter as ctk
import config
from ui.avatar import initial_avatar


ONLINE_TAB = "Đang online"
HISTORY_TAB = "Lịch sử"


class PeerSidebar(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_select_peer_cb,
        on_change_name_cb=None,
        on_toggle_activity_cb=None,
        on_quit_cb=None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "#FFFFFF")
        kwargs.setdefault("corner_radius", 18)
        super().__init__(master, **kwargs)
        self.on_select_peer_cb = on_select_peer_cb
        self.on_change_name_cb = on_change_name_cb
        self.on_toggle_activity_cb = on_toggle_activity_cb

        self._avatar_cache = []
        self._all_peers = {}
        self._unread_counts = {}
        self._last_activity = {}
        self._history_ids = set()
        self._active_peer_id = None
        self._my_status = getattr(config, "STATUS_ONLINE", "online")
        self._rebuilding = False
        self._presence_notices = deque(maxlen=3)
        self._presence_notice_timer = None

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(padx=14, pady=(14, 6), fill="x")

        self.title_label = ctk.CTkLabel(
            top_row,
            text="Chats",
            font=("Segoe UI", 20, "bold"),
            text_color="#453284",
        )
        self.title_label.pack(side="left")

        self.btn_activity = ctk.CTkButton(
            top_row,
            text="● Đang hoạt động",
            width=116,
            height=28,
            corner_radius=14,
            fg_color="#6A49FA",
            hover_color="#453284",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            command=self._handle_toggle_activity,
        )
        self.btn_activity.pack(side="right")

        self.name_box = ctk.CTkFrame(self, fg_color="#F5F3FF", corner_radius=12)
        self.name_box.pack(padx=12, pady=(0, 8), fill="x")

        self.name_entry = ctk.CTkEntry(
            self.name_box,
            height=30,
            corner_radius=10,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#D8CEFF",
            text_color="#1F2937",
            placeholder_text="Tên của bạn...",
        )
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(6, 4), pady=5)
        self.name_entry.bind("<Return>", lambda _e: self._submit_name())

        self.btn_rename = ctk.CTkButton(
            self.name_box,
            text="Đổi tên",
            width=60,
            height=30,
            corner_radius=10,
            fg_color="#6A49FA",
            hover_color="#453284",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            command=self._submit_name,
        )
        self.btn_rename.pack(side="right", padx=(0, 6), pady=5)

        self.search_entry = ctk.CTkEntry(
            self,
            height=32,
            corner_radius=16,
            fg_color="#C6E6FF",
            border_width=0,
            text_color="#1F2937",
            placeholder_text="Tìm kiếm...",
        )
        self.search_entry.pack(padx=12, pady=(0, 8), fill="x")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._rebuild_rows())

        self.peer_tabs = ctk.CTkSegmentedButton(
            self,
            values=[ONLINE_TAB, HISTORY_TAB],
            command=lambda _tab: self._rebuild_rows(),
            fg_color="#F5F3FF",
            selected_color="#D8CEFF",
            selected_hover_color="#CABBFF",
            unselected_color="#F5F3FF",
            unselected_hover_color="#E6E0FF",
            text_color="#453284",
            font=("Segoe UI", 12, "bold"),
        )
        self.peer_tabs.set(ONLINE_TAB)
        self.peer_tabs.pack(padx=12, pady=(0, 8), fill="x")

        self.presence_label = ctk.CTkLabel(
            self,
            text="",
            fg_color="#F5F3FF",
            corner_radius=8,
            text_color="#453284",
            font=("Segoe UI", 12),
            anchor="w",
            justify="left",
            padx=8,
            wraplength=200,
        )

        if on_quit_cb is not None:
            self.btn_quit = ctk.CTkButton(
                self,
                text="Thoát app",
                height=32,
                corner_radius=10,
                fg_color="#F5F3FF",
                hover_color="#E6E0FF",
                text_color="#453284",
                font=("Segoe UI", 12, "bold"),
                command=on_quit_cb,
            )
            self.btn_quit.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=12,
        )
        self.scroll_frame.pack(padx=6, pady=(0, 10), fill="both", expand=True)
        self._rebuild_rows()

    def show_presence_notice(self, message: str):
        if self._presence_notice_timer is not None:
            self.after_cancel(self._presence_notice_timer)
        self._presence_notices.append(message)
        self.presence_label.configure(text="\n".join(self._presence_notices))
        self.presence_label.pack(after=self.search_entry, fill="x", padx=12, pady=(0, 8))
        self._presence_notice_timer = self.after(5000, self._hide_presence_notice)

    def _hide_presence_notice(self):
        self._presence_notice_timer = None
        self._presence_notices.clear()
        self.presence_label.pack_forget()

    def destroy(self):
        if self._presence_notice_timer is not None:
            self.after_cancel(self._presence_notice_timer)
        super().destroy()

    def set_my_name(self, name: str):
        if name is not None:
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, name)

    def set_my_status(self, status: str):
        st = (status or "online").lower()
        self._my_status = "away" if st == "away" else "online"
        if self._my_status == "online":
            self.btn_activity.configure(
                text="● Đang hoạt động",
                fg_color="#6A49FA",
                hover_color="#453284",
                text_color="#FFFFFF",
            )
        else:
            self.btn_activity.configure(
                text="◐ Đang rời đi",
                fg_color="#F5F3FF",
                hover_color="#E6E0FF",
                text_color="#453284",
            )

    def _handle_toggle_activity(self):
        if callable(self.on_toggle_activity_cb):
            next_st = "away" if self._my_status == "online" else "online"
            self.on_toggle_activity_cb(next_st)

    def _submit_name(self):
        new_name = self.name_entry.get().strip()
        if new_name and callable(self.on_change_name_cb):
            self.on_change_name_cb(new_name)

    @staticmethod
    def _normalize_status(raw_status: str | None) -> str:
        st = (raw_status or "").strip().lower()
        return st if st in (*config.VALID_STATUSES, "offline") else "unknown"

    def _make_avatar(self, name: str, status: str) -> ctk.CTkImage:
        st = self._normalize_status(status)
        if st == "away":
            fill = (217, 119, 6, 255)
            dot_color = (234, 179, 8, 255)
        elif st in ("offline", "unknown"):
            fill = (107, 114, 128, 255)
            dot_color = (156, 163, 175, 255)
        else:
            fill = (106, 73, 250, 255)
            dot_color = (22, 163, 74, 255)

        ctk_img = initial_avatar(name, 34, fill, dot_color)
        self._avatar_cache.append(ctk_img)
        return ctk_img

    def update_peers(
        self,
        peers: dict,
        unread_counts: dict,
        active_peer_id: str,
        last_activity: dict | None = None,
        history_ids: set[str] | None = None,
    ):
        dedup = {}
        for raw_pid, info in (peers or {}).items():
            if not raw_pid:
                continue
            pid = str(raw_pid)
            if pid not in dedup:
                dedup[pid] = dict(info or {})
            else:
                dedup[pid].update(
                    {k: v for k, v in (info or {}).items() if v is not None}
                )

        self._all_peers = dedup
        self._unread_counts = {str(k): v for k, v in (unread_counts or {}).items()}
        self._last_activity = {
            str(k): float(v) for k, v in (last_activity or {}).items()
        }
        self._history_ids = history_ids or set()
        self._active_peer_id = str(active_peer_id) if active_peer_id else None
        self._rebuild_rows()

    def _on_pick_peer(self, pid: str):
        if callable(self.on_select_peer_cb):
            self.on_select_peer_cb(pid)

    def _add_peer_strip(self, peer_id: str, info: dict):
        name = info.get("name") or info.get("peer_name") or "Unknown"
        status = self._normalize_status(info.get("status"))
        status_txt = {"away": "Away", "offline": "Offline", "online": "Online", "unknown": "Chưa nhận HELLO"}[status]

        unread = int(self._unread_counts.get(peer_id, 0) or 0)
        is_active = peer_id == self._active_peer_id

        strip_fg = "#6A49FA" if is_active else "#F7F5FF"
        hover_fg = "#5536E8" if is_active else "#ECE7FF"
        name_fg = "#FFFFFF" if is_active else ("#6B7280" if status in ("offline", "unknown") else "#1F2937")

        badge = f" ({unread})" if unread > 0 else ""
        label_text = f"  {name}{badge} • {status_txt}"
        avatar_img = self._make_avatar(name, status)

        strip_btn = ctk.CTkButton(
            self.scroll_frame,
            image=avatar_img,
            compound="left",
            text=label_text,
            anchor="w",
            height=44,
            corner_radius=11,
            fg_color=strip_fg,
            hover_color=hover_fg,
            text_color=name_fg,
            font=("Segoe UI", 12, "bold" if is_active or unread > 0 else "normal"),
            command=lambda pid=peer_id: self._on_pick_peer(pid),
        )
        strip_btn.pack(fill="x", padx=4, pady=2)

    def _rebuild_rows(self):
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            for child in self.scroll_frame.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            self._avatar_cache.clear()

            query = self.search_entry.get().strip().lower()
            show_history = self.peer_tabs.get() == HISTORY_TAB
            ordered_ids = []

            for pid, info in self._all_peers.items():
                visible = (
                    pid in self._history_ids
                    if show_history
                    else info.get("status") in config.VALID_STATUSES
                )
                if not visible:
                    continue
                name = str(info.get("name") or info.get("peer_name") or "Unknown")
                if query and query not in name.lower():
                    continue
                ordered_ids.append(pid)

            ordered_ids.sort(
                key=lambda pid: (
                    self._last_activity.get(pid, 0.0),
                    str(
                        self._all_peers[pid].get("name")
                        or self._all_peers[pid].get("peer_name")
                        or ""
                    ).lower(),
                ),
                reverse=True,
            )

            for pid in ordered_ids:
                self._add_peer_strip(pid, self._all_peers[pid])
            if not ordered_ids:
                if query:
                    message = "Không tìm thấy người phù hợp"
                elif show_history:
                    message = "Chưa có lịch sử trò chuyện"
                else:
                    message = "Chưa có ai online"
                ctk.CTkLabel(self.scroll_frame, text=message, text_color="#6B7280").pack(pady=8)
        finally:
            self._rebuilding = False
