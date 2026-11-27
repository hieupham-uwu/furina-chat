import os
import platform
import subprocess
from tkinter import filedialog
import customtkinter as ctk
from PIL import Image
import config
from ui.sticker_picker import StickerPopup, _get_stickers_dir

MAX_MSG_CHARS = getattr(config, "MAX_MSG_CHARS", 4000)


def _get_downloads_dir() -> str:
    for attr in ("DOWNLOADS_DIR", "DOWNLOAD_DIR"):
        val = getattr(config, attr, None)
        if val:
            return val
    dir_name = getattr(config, "DOWNLOADS_DIR_NAME", "downloads")
    if os.path.isabs(dir_name):
        return dir_name
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, dir_name)


def _open_local_path(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


class ChatPanel(ctk.CTkFrame):
    def __init__(self, master, controller, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.controller = controller
        self._image_cache = []
        self._status_labels = {}

        # Khung tin nhắn lớn trắng bo góc giống giao diện mẫu
        self.messages_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#FFFFFF",
            corner_radius=18,
        )
        self.messages_scroll.pack(fill="both", expand=True, padx=0, pady=(0, 10))

        # Thanh báo lỗi nhẹ khi cần
        self.error_banner = ctk.CTkFrame(
            self, fg_color="#FEDADA", corner_radius=12
        )
        self.error_label = ctk.CTkLabel(
            self.error_banner,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#453284",
            anchor="w",
        )
        self.error_label.pack(side="left", padx=12, pady=5, fill="x", expand=True)
        ctk.CTkButton(
            self.error_banner,
            text="✕",
            width=22,
            height=22,
            corner_radius=11,
            fg_color="transparent",
            hover_color="#C6E6FF",
            text_color="#453284",
            command=self.hide_error,
        ).pack(side="right", padx=6)

        # Thanh tiến độ truyền file
        self.progress_frame = ctk.CTkFrame(
            self, height=34, fg_color="#FFFFFF", corner_radius=12
        )
        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="", font=("Segoe UI", 11), text_color="#453284"
        )
        self.progress_label.pack(side="left", padx=12)
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, progress_color="#6A49FA", fg_color="#C6E6FF"
        )
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=12)
        self.progress_bar.set(0)

        # Hàng điều khiển phía dưới giống giao diện mẫu: [📎 🖼️ 😊]  [Aa]  [➤]
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(fill="x", padx=0, pady=(0, 2))

        self.tools_box = ctk.CTkFrame(
            self.input_frame, fg_color="#FFFFFF", corner_radius=14
        )
        self.tools_box.pack(side="left", padx=(0, 8))

        self.btn_file = ctk.CTkButton(
            self.tools_box,
            text="📎",
            width=34,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#C6E6FF",
            text_color="#6A49FA",
            command=self._select_file,
        )
        self.btn_file.pack(side="left", padx=(4, 2), pady=3)

        self.btn_image = ctk.CTkButton(
            self.tools_box,
            text="🖼️",
            width=34,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#C6E6FF",
            text_color="#6A49FA",
            command=self._select_image,
        )
        self.btn_image.pack(side="left", padx=2, pady=3)

        self.btn_sticker = ctk.CTkButton(
            self.tools_box,
            text="😊",
            width=34,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#C6E6FF",
            text_color="#6A49FA",
            command=self._toggle_sticker_popup,
        )
        self.btn_sticker.pack(side="left", padx=(2, 4), pady=3)

        self.entry_msg = ctk.CTkEntry(
            self.input_frame,
            height=40,
            corner_radius=20,
            fg_color="#FFFFFF",
            border_width=0,
            text_color="#1F2937",
            placeholder_text="Aa",
        )
        self.entry_msg.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_msg.bind("<Return>", self._on_return)

        self.btn_send = ctk.CTkButton(
            self.input_frame,
            text="➤",
            width=42,
            height=42,
            corner_radius=21,
            fg_color="#6A49FA",
            hover_color="#453284",
            text_color="#FFFFFF",
            font=("Segoe UI", 14, "bold"),
            command=self._send_text,
        )
        self.btn_send.pack(side="right")

        # Ô sticker nổi nhỏ ngay phía trên nút sticker (không mở cửa sổ mới)
        self.sticker_popup = StickerPopup(
            self, on_select_sticker_cb=self._on_sticker_chosen
        )

    def show_error(self, message: str):
        self.error_label.configure(text=f"⚠️ {message}")
        if not self.error_banner.winfo_ismapped():
            self.error_banner.pack(
                fill="x", padx=0, pady=(0, 6), before=self.input_frame
            )

    def hide_error(self):
        if self.error_banner.winfo_ismapped():
            self.error_banner.pack_forget()

    def get_current_input(self) -> str:
        return self.entry_msg.get()

    def set_current_input(self, text: str):
        self.entry_msg.delete(0, "end")
        if text:
            self.entry_msg.insert(0, text)

    def set_header(self, _text: str = "", status: str = "", _status: str = ""):
        # Giữ phần khung chat sạch giống ảnh mẫu.
        # Nhận cả "status" (controller) và "_status" (kiểu cũ) để không vỡ lời gọi.
        return

    def _on_return(self, _event):
        self._send_text()
        return "break"

    def _send_text(self):
        text = self.entry_msg.get().strip()
        if not text:
            return
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để chat.")
            return
        if len(text) > MAX_MSG_CHARS:
            self.show_error(f"Tin nhắn vượt quá {MAX_MSG_CHARS} ký tự.")
            return

        self.hide_error()
        self.sticker_popup.hide_popup()
        self.entry_msg.delete(0, "end")
        self.entry_msg.focus_set()
        self.controller.send_text_message(text)

    def _toggle_sticker_popup(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để gửi sticker.")
            return
        self.update_idletasks()
        popup_h = 212
        x = max(4, self.tools_box.winfo_x() + self.btn_sticker.winfo_x())
        y = max(4, self.input_frame.winfo_y() - popup_h - 6)
        self.sticker_popup.toggle(x=x, y=y)

    def _on_sticker_chosen(self, pack: str, sticker_id: str):
        if self.controller and self.controller.has_active_peer():
            self.hide_error()
            self.entry_msg.focus_set()
            self.controller.send_sticker(pack, sticker_id)

    def _select_file(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để gửi tệp.")
            return
        file_path = filedialog.askopenfilename(title="Chọn tệp để gửi")
        if file_path:
            self.hide_error()
            self.entry_msg.focus_set()
            self.controller.send_file(file_path, media_type="FILE")

    def _select_image(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để gửi ảnh.")
            return
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh để gửi",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.webp")],
        )
        if file_path:
            self.hide_error()
            self.entry_msg.focus_set()
            self.controller.send_file(file_path, media_type="IMAGE")

    def _resolve_sticker_file(self, pack: str, sticker_id: str) -> str | None:
        stickers_root = _get_stickers_dir()
        exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        candidates = []
        if pack:
            for ext in exts:
                candidates.append(
                    os.path.join(stickers_root, pack, f"{sticker_id}{ext}")
                )
        for ext in exts:
            candidates.append(os.path.join(stickers_root, f"{sticker_id}{ext}"))
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def _resolve_media_file(self, msg: dict) -> str | None:
        for key in ("local_path", "filepath"):
            p = msg.get(key)
            if p and os.path.isfile(p):
                return p
        fname = msg.get("filename")
        if fname:
            cand = os.path.join(_get_downloads_dir(), fname)
            if os.path.isfile(cand):
                return cand
        return None

    def render_messages(self, history: list):
        self._image_cache.clear()
        self._status_labels.clear()
        for child in self.messages_scroll.winfo_children():
            child.destroy()

        for msg in history:
            self.append_single_message(msg)

    def update_message_status(self, msg_id: str, delivery_status: str):
        lbl = self._status_labels.get(msg_id)
        if lbl and lbl.winfo_exists():
            color = "#6B7280"
            if "chưa gửi" in delivery_status.lower() or "lỗi" in delivery_status.lower():
                color = "#DC2626"
            elif "đã xem" in delivery_status.lower():
                color = "#6A49FA"
            lbl.configure(text=delivery_status, text_color=color)

    def append_single_message(self, msg: dict):
        sender_name = msg.get("sender_name") or msg.get("sender") or "Unknown"
        msg_type = (msg.get("type") or "MSG").upper()
        is_me = bool(msg.get("is_me", False))
        msg_id = msg.get("msg_id")

        if msg_type == "SYSTEM":
            ctk.CTkLabel(
                self.messages_scroll,
                text=msg.get("text", ""),
                font=("Segoe UI", 12),
                text_color="#4B5563",
            ).pack(anchor="w", padx=12, pady=4)
            self._scroll_to_bottom()
            return

        anchor = "e" if is_me else "w"
        row_container = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        row_container.pack(anchor=anchor, pady=4, padx=12, fill="none")

        time_str = msg.get("timestamp", "")
        header_txt = f"{sender_name} • {time_str}" if time_str else sender_name
        ctk.CTkLabel(
            row_container,
            text=header_txt,
            font=("Segoe UI", 10, "bold"),
            text_color="#6B7280",
        ).pack(anchor=anchor, padx=4, pady=(0, 1))

        if msg_type == "MSG":
            # Chỉ tin nhắn văn bản của mình mới nằm trong khung màu tím #6A49FA
            bubble_fg = "#6A49FA" if is_me else "#F3F0FF"
            text_fg = "#FFFFFF" if is_me else "#1F2937"

            bubble = ctk.CTkFrame(
                row_container, fg_color=bubble_fg, corner_radius=14
            )
            bubble.pack(anchor=anchor, fill="none")

            ctk.CTkLabel(
                bubble,
                text=msg.get("text", ""),
                font=("Segoe UI", 12),
                text_color=text_fg,
                wraplength=440,
                justify="left",
            ).pack(anchor="w", padx=12, pady=7)

        elif msg_type == "STICKER":
            # Sticker hiển thị độc lập trên nền vùng chat, KHÔNG để trong khung màu tím
            pack = msg.get("pack", "cat")
            sid = msg.get("sticker_id", "")
            st_path = self._resolve_sticker_file(pack, sid)
            if st_path:
                try:
                    with Image.open(st_path) as im:
                        pil_img = im.copy()
                    w, h = pil_img.size
                    scale = min(145 / max(w, 1), 145 / max(h, 1), 1.0)
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img,
                        dark_image=pil_img,
                        size=(max(48, int(w * scale)), max(48, int(h * scale))),
                    )
                    self._image_cache.append(ctk_img)
                    ctk.CTkLabel(
                        row_container,
                        image=ctk_img,
                        text="",
                        fg_color="transparent",
                    ).pack(anchor=anchor, pady=2)
                except Exception:
                    ctk.CTkLabel(
                        row_container,
                        text=f"[Sticker: {pack}/{sid}]",
                        font=("Segoe UI", 12),
                    ).pack(anchor=anchor, pady=2)
            else:
                ctk.CTkLabel(
                    row_container,
                    text=f"[Sticker: {pack}/{sid}]",
                    font=("Segoe UI", 12),
                ).pack(anchor=anchor, pady=2)

        elif msg_type == "IMAGE":
            # Ảnh hiển thị full ảnh trên nền vùng chat, KHÔNG để trong khung màu tím
            fname = msg.get("filename", "image.png")
            media_path = self._resolve_media_file(msg)
            if media_path:
                try:
                    with Image.open(media_path) as im:
                        pil_img = im.copy()
                    w, h = pil_img.size
                    max_w, max_h = 420, 360
                    scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
                    disp_w = max(80, int(w * scale))
                    disp_h = max(80, int(h * scale))

                    ctk_img = ctk.CTkImage(
                        light_image=pil_img, dark_image=pil_img, size=(disp_w, disp_h)
                    )
                    self._image_cache.append(ctk_img)

                    btn_img = ctk.CTkButton(
                        row_container,
                        image=ctk_img,
                        text="",
                        corner_radius=12,
                        fg_color="transparent",
                        hover_color="#F3F0FF",
                        command=lambda p=media_path: _open_local_path(p),
                    )
                    btn_img.pack(anchor=anchor, pady=2)
                except Exception:
                    ctk.CTkLabel(
                        row_container, text=f"📷 {fname}", font=("Segoe UI", 12)
                    ).pack(anchor=anchor, pady=2)
            else:
                ctk.CTkLabel(
                    row_container, text=f"📷 {fname} (Đang nhận...)", font=("Segoe UI", 12)
                ).pack(anchor=anchor, pady=2)

        else:
            fname = msg.get("filename", "file")
            fsize = msg.get("size", 0)
            media_path = self._resolve_media_file(msg)
            file_card = ctk.CTkFrame(
                row_container, fg_color="#F3F0FF", corner_radius=12
            )
            file_card.pack(anchor=anchor, pady=2)

            ctk.CTkLabel(
                file_card, text=f"📁 {fname} ({fsize} bytes)", font=("Segoe UI", 12)
            ).pack(side="left", padx=12, pady=6)

            if media_path:
                ctk.CTkButton(
                    file_card,
                    text="Mở file",
                    width=64,
                    height=24,
                    corner_radius=8,
                    fg_color="#6A49FA",
                    hover_color="#453284",
                    command=lambda p=media_path: _open_local_path(p),
                ).pack(side="right", padx=(0, 8), pady=6)

        delivery_status = msg.get("delivery_status")
        if not delivery_status:
            delivery_status = "Đã gửi" if is_me else "Đã nhận"

        status_color = "#6B7280"
        if "chưa gửi" in delivery_status.lower() or "lỗi" in delivery_status.lower():
            status_color = "#DC2626"
        elif "đã xem" in delivery_status.lower():
            status_color = "#6A49FA"

        lbl_status = ctk.CTkLabel(
            row_container,
            text=delivery_status,
            font=("Segoe UI", 10),
            text_color=status_color,
        )
        lbl_status.pack(anchor=anchor, padx=4, pady=(1, 0))
        if msg_id:
            self._status_labels[msg_id] = lbl_status

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        try:
            self.messages_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def update_progress(self, percent: float, text: str):
        clamped = max(0.0, min(1.0, float(percent)))
        if clamped < 1.0:
            if not self.progress_frame.winfo_ismapped():
                self.progress_frame.pack(
                    fill="x", padx=0, pady=(0, 6), before=self.input_frame
                )
            self.progress_bar.set(clamped)
            self.progress_label.configure(
                text=text or f"Đang truyền: {int(clamped * 100)}%"
            )
        else:
            self.progress_bar.set(1.0)
            self.progress_label.configure(text=text or "Hoàn thành 100%")
            self.after(1500, self._hide_progress)

    def _hide_progress(self):
        if self.progress_frame.winfo_ismapped():
            self.progress_frame.pack_forget()