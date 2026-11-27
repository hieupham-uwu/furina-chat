import os
import platform
import subprocess
from textwrap import wrap
from tkinter import TclError, filedialog
import customtkinter as ctk
from PIL import Image, ImageDraw
import config
from ui.avatar import initial_avatar
from ui.sticker_picker import _get_stickers_dir

MAX_MSG_CHARS = config.MAX_MESSAGE_LENGTH
TYPE_MSG = getattr(config, "TYPE_MSG", "MSG")
TYPE_STICKER = getattr(config, "TYPE_STICKER", "STICKER")
TYPE_IMAGE = getattr(config, "TYPE_IMAGE", "IMAGE")
TYPE_FILE = getattr(config, "TYPE_FILE", "FILE")


def _get_downloads_dir() -> str:
    val = getattr(config, "DOWNLOADS_DIR", None)
    if val:
        return str(val)
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


def _attachment_icon(kind):
    image = Image.new("RGBA", (72, 72))
    draw = ImageDraw.Draw(image)
    color = "#6A49FA"
    if kind == "file":
        draw.line([(21, 22), (21, 46), (24, 54), (33, 59), (44, 55), (48, 46),
                   (48, 20), (45, 14), (37, 13), (31, 19), (31, 44), (36, 48),
                   (40, 44), (40, 23)], fill=color, width=5, joint="curve")
    elif kind == "image":
        draw.rounded_rectangle((10, 13, 62, 59), radius=7, outline=color, width=5)
        draw.ellipse((21, 22, 30, 31), fill=color)
        draw.line([(14, 52), (34, 35), (43, 44), (53, 33), (59, 40)], fill=color, width=4, joint="curve")
    else:
        draw.rounded_rectangle((12, 12, 60, 60), radius=13, outline=color, width=5)
        draw.ellipse((24, 26, 29, 31), fill=color)
        draw.ellipse((43, 26, 48, 31), fill=color)
        draw.arc((24, 30, 48, 48), 0, 180, fill=color, width=4)
    return ctk.CTkImage(light_image=image, size=(20, 20))


def _size_mb(size):
    return "<0,01 MB" if 0 < size < 10_000 else f"{size / 1_000_000:.2f} MB".replace(".", ",")


def _sender_header(name, timestamp):
    return f"{name} • {timestamp}" if timestamp else name


class ChatPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        controller,
        on_toggle_sticker_cb=None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.controller = controller
        self.on_toggle_sticker_cb = on_toggle_sticker_cb
        self._image_cache = []
        self._status_labels = {}
        self._sender_widgets = {}
        self._file_rows = {}
        self._transfer_widgets = {}
        self._scroll_after_id = None
        self._empty_history_label = None

        self.header_bar = ctk.CTkFrame(
            self, fg_color="#FFFFFF", corner_radius=14, height=42
        )
        self.header_bar.pack(fill="x", padx=0, pady=(0, 8))
        self.header_bar.pack_propagate(False)

        self.btn_leave_chat = ctk.CTkButton(
            self.header_bar,
            text="Rời chat",
            width=72,
            corner_radius=12,
            fg_color="#F5F3FF",
            hover_color="#E6E0FF",
            text_color="#453284",
            font=("Segoe UI", 12, "bold"),
            command=self._leave_chat,
        )

        self.header_dot = ctk.CTkLabel(
            self.header_bar,
            text="●",
            font=("Segoe UI", 12, "bold"),
            text_color="#16A34A",
        )
        self.header_dot.pack(side="left", padx=(14, 6))

        self.header_label = ctk.CTkLabel(
            self.header_bar,
            text="Chưa chọn cuộc trò chuyện",
            font=("Segoe UI", 13, "bold"),
            text_color="#453284",
        )
        self.header_label.pack(side="left")

        self.header_status_label = ctk.CTkLabel(
            self.header_bar,
            text="",
            font=("Segoe UI", 11),
            text_color="#6B7280",
        )
        self.header_status_label.pack(side="left", padx=8)

        self.header_address_label = ctk.CTkLabel(
            self.header_bar, text="", font=("Segoe UI", 11), text_color="#6B7280",
        )
        self.header_address_label.pack(side="right", padx=(0, 8))

        self.messages_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#FFFFFF",
            corner_radius=18,
        )
        self.messages_scroll.pack(fill="both", expand=True, padx=0, pady=(0, 10))

        self.error_banner = ctk.CTkFrame(self, fg_color="#FEDADA", corner_radius=12)
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

        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(fill="x", padx=0, pady=(0, 2))

        self.tools_box = ctk.CTkFrame(
            self.input_frame, fg_color="#FFFFFF", corner_radius=14
        )
        self.tools_box.pack(side="left", padx=(0, 8))

        for kind, command in (("file", self._select_file), ("image", self._select_image),
                              ("sticker", self._on_sticker_button_click)):
            button = ctk.CTkButton(
                self.tools_box, width=34, height=34, corner_radius=10,
                image=_attachment_icon(kind), text="", anchor="center",
                fg_color="#FFFFFF", hover_color="#EDE9FE", command=command,
            )
            button.pack(side="left", padx=2, pady=3)
            setattr(self, f"btn_{kind}", button)

        self.entry_msg = ctk.CTkTextbox(
            self.input_frame,
            height=44,
            corner_radius=20,
            fg_color="#FFFFFF",
            border_width=0,
            text_color="#1F2937",
            wrap="word",
        )
        self.entry_msg.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_msg.bind("<Return>", self._on_return)
        self.entry_msg.bind("<Control-v>", self._paste_text)
        self.entry_msg.bind("<<Paste>>", self._paste_text)
        self.entry_msg.bind("<KeyPress>", self._limit_input)

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

    def set_header(self, title_text: str = "", status: str = "", *, ip=None, tcp_port=None):
        self.header_label.configure(text=title_text or "Chưa chọn cuộc trò chuyện")
        self.header_address_label.configure(text=f"{ip}:{tcp_port}" if ip and tcp_port else "")
        if title_text:
            self.btn_leave_chat.pack(side="right", padx=(0, 10), before=self.header_dot)
        else:
            self.btn_leave_chat.pack_forget()
        st = (status or "").lower()
        if st == "away":
            self.header_dot.configure(text_color="#EAB308")
            self.header_status_label.configure(text="(Away)", text_color="#A16207")
        elif st == "online":
            self.header_dot.configure(text_color="#16A34A")
            self.header_status_label.configure(text="(Online)", text_color="#15803D")
        elif st == "offline":
            self.header_dot.configure(text_color="#9CA3AF")
            self.header_status_label.configure(text="(Offline)", text_color="#6B7280")
        elif st == "unknown":
            self.header_dot.configure(text_color="#9CA3AF")
            self.header_status_label.configure(text="(Chưa nhận HELLO)", text_color="#6B7280")
        else:
            self.header_dot.configure(text_color="#6B7280")
            self.header_status_label.configure(text="", text_color="#6B7280")

    def _leave_chat(self):
        if self.controller:
            self.controller.leave_active_chat()

    def show_error(self, message: str):
        msg = str(message or "Đã xảy ra lỗi.")
        if not msg.lower().startswith("cảnh báo:"):
            msg = f"Cảnh báo: {msg}"
        self.error_label.configure(text=f"⚠️ {msg}")
        if not self.error_banner.winfo_ismapped():
            self.error_banner.pack(
                fill="x", padx=0, pady=(0, 6), before=self.input_frame
            )

    def hide_error(self):
        if self.error_banner.winfo_ismapped():
            self.error_banner.pack_forget()

    def get_current_input(self) -> str:
        return self.entry_msg.get("1.0", "end-1c")

    def set_current_input(self, text: str):
        self.entry_msg.delete("1.0", "end")
        if text:
            self.entry_msg.insert("1.0", text[:MAX_MSG_CHARS])

    def _available_input(self, entry):
        selection = entry.tag_ranges("sel")
        selected = entry.get(*selection) if selection else ""
        return max(0, MAX_MSG_CHARS - len(self.get_current_input()) + len(selected))

    def _limit_input(self, event):
        if event.char.isprintable() and len(event.char) > self._available_input(event.widget):
            return "break"

    def _paste_text(self, event):
        entry = event.widget
        try:
            pasted = entry.clipboard_get()
        except TclError:
            return "break"

        available = self._available_input(entry)
        if pasted and available:
            selection = entry.tag_ranges("sel")
            if selection:
                entry.delete(*selection)
                entry.mark_set("insert", selection[0])
            entry.insert("insert", pasted[:available])
        if len(pasted) > available:
            self.show_error(f"Ô nhập chỉ chứa tối đa {MAX_MSG_CHARS} ký tự.")
        return "break"

    def _on_return(self, _event):
        self._send_text()
        return "break"

    def _send_text(self):
        raw_text = self.get_current_input()
        if len(raw_text) > MAX_MSG_CHARS:
            self.show_error(
                f"Tin nhắn vượt quá giới hạn {MAX_MSG_CHARS} ký tự ({len(raw_text)}/{MAX_MSG_CHARS})."
            )
            return
        text = raw_text.strip()
        if not text:
            return
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để chat.")
            return

        self.hide_error()
        self.set_current_input("")
        self.entry_msg.focus_set()
        self.controller.send_text_message(text)

    def _on_sticker_button_click(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người trước khi gửi sticker.")
        else:
            self.hide_error()
        if callable(self.on_toggle_sticker_cb):
            self.on_toggle_sticker_cb(self.btn_sticker)

    def _select_file(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để gửi tệp.")
            return
        file_path = filedialog.askopenfilename(title="Chọn tệp để gửi")
        if file_path:
            self.hide_error()
            self.entry_msg.focus_set()
            self.controller.send_file(file_path, media_type=TYPE_FILE)

    def _select_image(self):
        if not (self.controller and self.controller.has_active_peer()):
            self.show_error("Hãy chọn một người để gửi ảnh.")
            return
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh để gửi",
            filetypes=[("Tệp hình ảnh", "*.png *.jpg *.jpeg *.gif *.webp")],
        )
        if file_path:
            self.hide_error()
            self.entry_msg.focus_set()
            self.controller.send_file(file_path, media_type=TYPE_IMAGE)

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
        for root, _dirs, files in os.walk(stickers_root):
            for fname in files:
                base, ext = os.path.splitext(fname)
                if base == sticker_id and ext.lower() in exts:
                    return os.path.join(root, fname)
        return None

    def _resolve_media_file(self, msg: dict) -> str | None:
        for key in ("local_path", "filepath"):
            p = msg.get(key)
            if p and os.path.isfile(p):
                return p
        if msg.get("transfer_id"):
            return None
        fname = msg.get("filename")
        if fname:
            cand = os.path.join(_get_downloads_dir(), fname)
            if os.path.isfile(cand):
                return cand
        return None

    def render_messages(self, history: list):
        self.messages_scroll._parent_canvas.yview_moveto(0)
        self._image_cache.clear()
        self._status_labels.clear()
        self._sender_widgets.clear()
        self._file_rows.clear()
        self._transfer_widgets.clear()
        for child in self.messages_scroll.winfo_children():
            child.destroy()
        self._empty_history_label = None

        for msg in history:
            self.append_single_message(msg)
        if not history:
            self._empty_history_label = ctk.CTkLabel(
                self.messages_scroll, text="Chưa có tin nhắn", text_color="#6B7280",
            )
            self._empty_history_label.pack(pady=16)
        self._scroll_to_bottom()

    def update_message_status(self, msg_id: str, delivery_status: str):
        lbl = self._status_labels.get(msg_id)
        if lbl and lbl.winfo_exists():
            color = "#6B7280"
            if "chưa gửi" in delivery_status.lower() or "lỗi" in delivery_status.lower():
                color = "#DC2626"
            elif "đã xem" in delivery_status.lower():
                color = "#6A49FA"
            lbl.configure(text=delivery_status, text_color=color)

    def update_sender_names(self, messages):
        avatar = None
        for msg in messages:
            widgets = self._sender_widgets.get(msg.get("msg_id"))
            if not widgets:
                continue
            header, avatar_label = widgets
            name = msg["sender_name"]
            header.configure(text=_sender_header(name, msg.get("timestamp")))
            if avatar_label is not None:
                if avatar is None:
                    avatar = initial_avatar(name, 26, "#6A49FA")
                avatar_label.configure(image=avatar)

    def append_single_message(self, msg: dict, *, before=None, scroll=True):
        if self._empty_history_label is not None:
            self._empty_history_label.destroy()
            self._empty_history_label = None
        sender_name = msg.get("sender_name") or msg.get("sender") or "Unknown"
        msg_type = (msg.get("type") or TYPE_MSG).upper()
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
        row_outer = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        pack_location = {"before": before} if before is not None else {}
        row_outer.pack(anchor=anchor, pady=4, padx=12, fill="none", **pack_location)

        row_container = ctk.CTkFrame(row_outer, fg_color="transparent")
        row_container.pack(side="left", anchor=anchor)

        header = ctk.CTkLabel(
            row_container,
            text=_sender_header(sender_name, msg.get("timestamp")),
            font=("Segoe UI", 10, "bold"),
            text_color="#6B7280",
        )
        header.pack(anchor=anchor, padx=4, pady=(0, 1))

        if msg_type == TYPE_MSG:
            bubble_fg = "#6A49FA" if is_me else "#F3F0FF"
            text_fg = "#FFFFFF" if is_me else "#1F2937"

            bubble = ctk.CTkFrame(row_container, fg_color=bubble_fg, corner_radius=14)
            bubble.pack(anchor=anchor, fill="none")

            text = msg.get("text", "")
            wraplength = 440
            if len(text) > 500:
                # Keep Tk from measuring a single very long line on Windows.
                wraplength = 0
                text = "\n".join(
                    "\n".join(wrap(line, width=28, replace_whitespace=False, drop_whitespace=False))
                    for line in text.split("\n")
                )
            ctk.CTkLabel(
                bubble,
                text=text,
                font=("Segoe UI", 12),
                text_color=text_fg,
                wraplength=wraplength,
                justify="left",
            ).pack(anchor="w", padx=12, pady=7)

        elif msg_type == TYPE_STICKER:
            pack = msg.get("pack", "cat")
            sid = msg.get("sticker_id", "")
            st_path = self._resolve_sticker_file(pack, sid)
            if st_path:
                try:
                    with Image.open(st_path) as im:
                        pil_img = im.convert("RGBA").copy()
                    w, h = pil_img.size
                    scale = min(130 / max(w, 1), 130 / max(h, 1), 1.0)
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img,
                        dark_image=pil_img,
                        size=(max(56, int(w * scale)), max(56, int(h * scale))),
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
                        text=f"[Sticker: {sid or pack}]",
                        font=("Segoe UI", 13, "bold"),
                        text_color="#6A49FA",
                        fg_color="transparent",
                    ).pack(anchor=anchor, pady=2)
            else:
                ctk.CTkLabel(
                    row_container,
                    text=f"✨ {(sid or 'Sticker').upper()}",
                    font=("Segoe UI", 14, "bold"),
                    text_color="#453284",
                    fg_color="transparent",
                ).pack(anchor=anchor, padx=8, pady=4)

        elif msg_type == TYPE_IMAGE:
            fname = msg.get("filename", "image.png")
            media_path = self._resolve_media_file(msg)
            if media_path:
                try:
                    with Image.open(media_path) as im:
                        im.thumbnail((840, 720))
                        pil_img = im.convert("RGBA")
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
                    row_container, text=f"📷 {fname}", font=("Segoe UI", 12)
                ).pack(anchor=anchor, pady=2)
            ctk.CTkLabel(
                row_container, text=_size_mb(msg.get("size", 0)), font=("Segoe UI", 10),
            ).pack(anchor=anchor, padx=4)

        else:
            fname = msg.get("filename", "file")
            fsize = msg.get("size", 0)
            media_path = self._resolve_media_file(msg)
            file_card = ctk.CTkFrame(
                row_container, fg_color="#F3F0FF", corner_radius=12
            )
            file_card.pack(anchor=anchor, pady=2)

            ctk.CTkLabel(
                file_card, text=f"📁 {fname} ({_size_mb(fsize)})", font=("Segoe UI", 12)
            ).pack(side="left", padx=12, pady=6)

            if media_path:
                ctk.CTkButton(
                    file_card,
                    text="Mở tệp",
                    width=64,
                    height=24,
                    corner_radius=8,
                    fg_color="#6A49FA",
                    hover_color="#453284",
                    command=lambda p=media_path: _open_local_path(p),
                ).pack(side="right", padx=(0, 8), pady=6)

        if msg_type in (TYPE_FILE, TYPE_IMAGE) and msg_id:
            self._file_rows[msg_id] = row_outer
            if "transfer_progress" in msg:
                self._add_transfer_controls(row_container, anchor, msg)

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

        avatar_label = None
        if is_me:
            av_img = initial_avatar(sender_name, 26, "#6A49FA")
            self._image_cache.append(av_img)
            avatar_label = ctk.CTkLabel(
                row_outer,
                image=av_img,
                text="",
                fg_color="transparent",
            )
            avatar_label.pack(side="right", anchor="s", padx=(6, 0), pady=(0, 14))

        if msg_id:
            self._sender_widgets[msg_id] = (header, avatar_label)

        if scroll:
            self._scroll_to_bottom()

    def _add_transfer_controls(self, row, anchor, msg):
        controls = ctk.CTkFrame(row, fg_color="transparent")
        controls.pack(anchor=anchor, padx=4, pady=(4, 0))
        bar = ctk.CTkProgressBar(controls, width=110, height=7, progress_color="#6A49FA")
        bar.pack(side="left", padx=(0, 6))
        label = ctk.CTkLabel(controls, text="", width=32, font=("Segoe UI", 10))
        label.pack(side="left")
        cancel = None
        if msg.get("transfer_cancellable"):
            cancel = ctk.CTkButton(
                controls, text="Hủy gửi", width=64, height=22,
                fg_color="#F3F0FF", hover_color="#EDE9FE", text_color="#453284",
                command=lambda: self.controller.cancel_file(msg["transfer_id"]),
            )
            cancel.pack(side="left", padx=(6, 0))
        self._transfer_widgets[msg["msg_id"]] = (controls, bar, label, cancel)
        self.update_transfer(msg)

    def update_transfer(self, msg):
        msg_id = msg["msg_id"]
        self.update_message_status(msg_id, msg["delivery_status"])
        widgets = self._transfer_widgets.get(msg_id)
        if not widgets:
            return
        controls, bar, label, cancel = widgets
        progress = msg.get("transfer_progress")
        if progress is None and not msg.get("acked"):
            self._remove_transfer_controls(msg_id, controls)
            return

        display_progress = 1.0 if progress is None else progress
        bar.set(display_progress)
        label.configure(text=f"{display_progress:.0%}")
        if cancel and not msg.get("transfer_cancellable"):
            cancel.pack_forget()
        if progress is None:
            self.after(1000, self._remove_transfer_controls, msg_id, controls)

    def _remove_transfer_controls(self, msg_id, controls):
        widgets = self._transfer_widgets.get(msg_id)
        if widgets and widgets[0] is controls:
            del self._transfer_widgets[msg_id]
            controls.destroy()

    def refresh_file_message(self, msg):
        msg_id = msg["msg_id"]
        row = self._file_rows.get(msg_id)
        if row is None:
            return
        siblings = self.messages_scroll.pack_slaves()
        index = siblings.index(row) + 1
        before = siblings[index] if index < len(siblings) else None
        self._transfer_widgets.pop(msg_id, None)
        row.destroy()
        self.append_single_message({**msg, "transfer_progress": 1.0}, before=before, scroll=False)
        self.update_transfer(msg)

    def _scroll_to_bottom(self):
        if self._scroll_after_id is None:
            self._scroll_after_id = self.after_idle(self._apply_history_scroll)

    def _apply_history_scroll(self):
        self.messages_scroll.update_idletasks()
        self._scroll_after_id = None
        canvas = self.messages_scroll._parent_canvas
        bounds = canvas.bbox("all")
        if bounds:
            canvas.configure(scrollregion=bounds)
            canvas.yview_moveto(1.0 if bounds[3] - bounds[1] > canvas.winfo_height() else 0.0)
