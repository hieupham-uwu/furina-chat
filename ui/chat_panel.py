import os
import platform
import subprocess
from textwrap import wrap
from tkinter import TclError, filedialog
import customtkinter as ctk
from PIL import Image, ImageDraw
import config
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


def _get_assets_dir() -> str:
    val = getattr(config, "ASSETS_DIR", None)
    if val:
        return str(val)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets")


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


def _make_avatar_pil(
    avatar_source=None, sender_name: str = "Me", size: int = 26
) -> Image.Image:
    if isinstance(avatar_source, Image.Image):
        return avatar_source.convert("RGBA").resize((size, size))
    if isinstance(avatar_source, str) and os.path.isfile(avatar_source):
        try:
            with Image.open(avatar_source) as im:
                return im.convert("RGBA").resize((size, size))
        except Exception:
            pass

    assets_dir = _get_assets_dir()
    for fname in ("my_avatar.png", "my_avatar.jpg", "avatar.png", "avatar.jpg"):
        cand = os.path.join(assets_dir, fname)
        if os.path.isfile(cand):
            try:
                with Image.open(cand) as im:
                    return im.convert("RGBA").resize((size, size))
            except Exception:
                pass

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size - 1, size - 1], fill=(106, 73, 250, 255))
    letter = (sender_name or "M").strip()[:1].upper() or "M"
    draw.text((size // 2 - 3, size // 2 - 6), letter, fill=(255, 255, 255, 255))
    return img


class ChatPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        controller,
        on_toggle_sticker_cb=None,
        my_avatar=None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.controller = controller
        self.on_toggle_sticker_cb = on_toggle_sticker_cb
        self.my_avatar = my_avatar
        self._image_cache = []
        self._status_labels = {}
        self._scroll_after_id = None
        self._empty_history_label = None

        self.header_bar = ctk.CTkFrame(
            self, fg_color="#FFFFFF", corner_radius=14, height=42
        )
        self.header_bar.pack(fill="x", padx=0, pady=(0, 8))
        self.header_bar.pack_propagate(False)

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

        self.btn_change_avatar = ctk.CTkButton(
            self.header_bar,
            text="Đổi AVT",
            width=72,
            height=28,
            corner_radius=10,
            fg_color="#EDE9FE",
            hover_color="#DDD6FE",
            text_color="#453284",
            font=("Segoe UI", 11, "bold"),
            command=self._choose_avatar,
        )
        self.btn_change_avatar.pack(side="right", padx=(4, 10))

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

        self.progress_frame = ctk.CTkFrame(
            self, height=34, fg_color="#FFFFFF", corner_radius=12
        )
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=("Segoe UI", 11),
            text_color="#453284",
        )
        self.progress_label.pack(side="left", padx=12)
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, progress_color="#6A49FA", fg_color="#C6E6FF"
        )
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=12)
        self.progress_bar.set(0)

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
            fg_color="#EDE9FE",
            hover_color="#DDD6FE",
            text_color="#453284",
            command=self._on_sticker_button_click,
        )
        self.btn_sticker.pack(side="left", padx=(2, 4), pady=3)

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

    def _choose_avatar(self):
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh đại diện của bạn",
            filetypes=[("Tệp hình ảnh", "*.png *.jpg *.jpeg *.gif *.webp")],
        )
        if file_path:
            self.set_my_avatar(file_path)

    def set_my_avatar(self, avatar_source):
        self.my_avatar = avatar_source
        if self.controller and self.controller.has_active_peer():
            with self.controller.state.lock:
                pid = self.controller.state.active_peer_id
                history = list(self.controller.state.chat_history.get(pid, []))
            self.render_messages(history)

    def set_header(self, title_text: str, status: str = ""):
        self.header_label.configure(text=title_text or "Chưa chọn cuộc trò chuyện")
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
        else:
            self.header_dot.configure(text_color="#6B7280")
            self.header_status_label.configure(text="", text_color="#6B7280")

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
            if self.controller:
                self.controller.record_user_activity(auto_back_online=True)
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

    def append_single_message(self, msg: dict):
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
        row_outer.pack(anchor=anchor, pady=4, padx=12, fill="none")

        row_container = ctk.CTkFrame(row_outer, fg_color="transparent")
        row_container.pack(side="left", anchor=anchor)

        time_str = msg.get("timestamp", "")
        header_txt = f"{sender_name} • {time_str}" if time_str else sender_name
        ctk.CTkLabel(
            row_container,
            text=header_txt,
            font=("Segoe UI", 10, "bold"),
            text_color="#6B7280",
        ).pack(anchor=anchor, padx=4, pady=(0, 1))

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
                        pil_img = im.convert("RGBA").copy()
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

        if is_me:
            av_src = msg.get("avatar") or self.my_avatar
            av_pil = _make_avatar_pil(av_src, sender_name=sender_name, size=26)
            av_img = ctk.CTkImage(light_image=av_pil, dark_image=av_pil, size=(26, 26))
            self._image_cache.append(av_img)
            ctk.CTkLabel(
                row_outer,
                image=av_img,
                text="",
                fg_color="transparent",
            ).pack(side="right", anchor="s", padx=(6, 0), pady=(0, 14))

        self._scroll_to_bottom()

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
