import customtkinter as ctk
from PIL import Image, ImageDraw


class PeerSidebar(ctk.CTkFrame):
    def __init__(self, master, on_select_peer_cb, on_change_status_cb=None, **kwargs):
        kwargs.setdefault("fg_color", "#FFFFFF")
        kwargs.setdefault("corner_radius", 18)
        super().__init__(master, **kwargs)
        self.on_select_peer_cb = on_select_peer_cb
        self.on_change_status_cb = on_change_status_cb
        self.peer_rows = {}
        self._avatar_cache = []
        self._all_peers = {}
        self._unread_counts = {}
        self._active_peer_id = None
        self._my_status = "online"

        self.title_label = ctk.CTkLabel(
            self,
            text="Chats",
            font=("Segoe UI", 22, "bold"),
            text_color="#453284",
        )
        self.title_label.pack(padx=16, pady=(16, 8), anchor="w")

        self.search_entry = ctk.CTkEntry(
            self,
            height=34,
            corner_radius=17,
            fg_color="#C6E6FF",
            border_width=0,
            text_color="#1F2937",
            placeholder_text="Search...",
        )
        self.search_entry.pack(padx=14, pady=(0, 10), fill="x")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._rebuild_rows())

        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=12,
        )
        self.scroll_frame.pack(padx=8, pady=(0, 8), fill="both", expand=True)

        # Nút đổi trạng thái ở góc dưới trái giống giao diện mẫu
        self.btn_status = ctk.CTkButton(
            self,
            text="Đổi trạng thái",
            height=36,
            corner_radius=18,
            fg_color="#6A49FA",
            hover_color="#453284",
            text_color="#FFFFFF",
            font=("Segoe UI", 12, "bold"),
            command=self._toggle_status,
        )
        self.btn_status.pack(side="left", padx=14, pady=(4, 14))

    def _toggle_status(self):
        next_status = "away" if self._my_status == "online" else "online"
        self._my_status = next_status
        if callable(self.on_change_status_cb):
            self.on_change_status_cb(next_status)

    def _make_avatar_with_dot(self, name: str, status: str) -> ctk.CTkImage:
        """Avatar có chấm tròn kế bên/góc dưới phải: xanh (online), vàng (away), xám (offline)."""
        size = 40
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.ellipse([1, 1, size - 5, size - 5], fill=(106, 73, 250, 255))
        initial = (name.strip()[:1] or "?").upper()
        draw.text((13, 10), initial, fill=(255, 255, 255, 255))

        st = (status or "offline").lower()
        if st == "online":
            dot_color = (34, 197, 94, 255)
        elif st == "away":
            dot_color = (234, 179, 8, 255)
        else:
            dot_color = (156, 163, 175, 255)

        dot_r = 6
        cx = size - dot_r - 1
        cy = size - dot_r - 1
        draw.ellipse(
            [cx - dot_r - 1, cy - dot_r - 1, cx + dot_r + 1, cy + dot_r + 1],
            fill=(255, 255, 255, 255),
        )
        draw.ellipse(
            [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
            fill=dot_color,
        )

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        self._avatar_cache.append(ctk_img)
        return ctk_img

    def update_peers(self, peers: dict, unread_counts: dict, active_peer_id: str):
        self._all_peers = dict(peers or {})
        self._unread_counts = dict(unread_counts or {})
        self._active_peer_id = active_peer_id
        self._rebuild_rows()

    def _rebuild_rows(self):
        for row in self.peer_rows.values():
            row.destroy()
        self.peer_rows.clear()
        self._avatar_cache.clear()

        query = self.search_entry.get().strip().lower()

        for peer_id, info in self._all_peers.items():
            name = info.get("name", "Unknown")
            if query and query not in name.lower():
                continue

            status = info.get("status", "offline")
            unread = self._unread_counts.get(peer_id, 0)
            is_active = peer_id == self._active_peer_id

            row_bg = "#6A49FA" if is_active else "#F7F5FF"
            text_color = "#FFFFFF" if is_active else "#1F2937"

            row = ctk.CTkFrame(self.scroll_frame, fg_color=row_bg, corner_radius=12)
            row.pack(fill="x", padx=2, pady=3)

            avatar_img = self._make_avatar_with_dot(name, status)
            avatar_lbl = ctk.CTkLabel(
                row, image=avatar_img, text="", width=42, height=42
            )
            avatar_lbl.pack(side="left", padx=(8, 6), pady=5)

            badge_text = f"  ({unread})" if unread > 0 else ""
            name_btn = ctk.CTkButton(
                row,
                text=f"{name}{badge_text}",
                anchor="w",
                fg_color="transparent",
                hover_color="#453284" if is_active else "#EDE9FE",
                text_color=text_color,
                font=("Segoe UI", 12, "bold" if is_active or unread > 0 else "normal"),
                command=lambda pid=peer_id: self.on_select_peer_cb(pid),
            )
            name_btn.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=5)

            avatar_lbl.bind(
                "<Button-1>", lambda _e, pid=peer_id: self.on_select_peer_cb(pid)
            )
            row.bind("<Button-1>", lambda _e, pid=peer_id: self.on_select_peer_cb(pid))

            self.peer_rows[peer_id] = row