import os
import customtkinter as ctk
from PIL import Image, ImageDraw
import config

DEFAULT_STICKERS = [
    ("cat", "hello", "Hello", (167, 139, 250, 255)),
    ("cat", "love", "Love", (244, 114, 182, 255)),
    ("cat", "laugh", "Haha", (250, 204, 21, 255)),
    ("cat", "ok", "OK", (74, 222, 128, 255)),
    ("cat", "sad", "Sad", (96, 165, 250, 255)),
    ("cat", "wow", "Wow", (251, 146, 60, 255)),
]


def _get_stickers_dir() -> str:
    val = getattr(config, "STICKERS_DIR", None)
    if val:
        return str(val)
    assets_dir = getattr(config, "ASSETS_DIR", None)
    if assets_dir:
        return os.path.join(str(assets_dir), "stickers")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets", "stickers")


def _make_sticker_image(
    label: str, bg_rgba: tuple[int, int, int, int]
) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=14, fill=bg_rgba)
    text = (label or "ST")[:6]
    draw.text((12, 24), text, fill=(30, 20, 60, 255))
    return img


class StickerPopup(ctk.CTkFrame):
    """Khung chọn sticker màu tím nổi phía trên thanh nhập."""

    def __init__(self, master, on_select_sticker_cb, **kwargs):
        kwargs.setdefault("fg_color", "#453284")
        kwargs.setdefault("corner_radius", 16)
        kwargs.setdefault("border_width", 2)
        kwargs.setdefault("border_color", "#C4B5FD")
        super().__init__(master, **kwargs)
        self.on_select_sticker_cb = on_select_sticker_cb
        self._images = []
        self._is_open = False

        top_bar = ctk.CTkFrame(self, fg_color="#6A49FA", corner_radius=12, height=34)
        top_bar.pack(fill="x", padx=8, pady=(8, 4))
        top_bar.pack_propagate(False)

        ctk.CTkLabel(
            top_bar,
            text="Chọn sticker",
            font=("Segoe UI", 12, "bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            top_bar,
            text="✕",
            width=24,
            height=24,
            corner_radius=12,
            fg_color="#453284",
            hover_color="#DC2626",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            command=self.hide_popup,
        ).pack(side="right", padx=4)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#5B3FD9",
            corner_radius=12,
        )
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.load_stickers()

    def _collect_disk_stickers(self):
        root_dir = _get_stickers_dir()
        if not os.path.isdir(root_dir):
            return []
        exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        found = []
        for entry in sorted(os.listdir(root_dir)):
            full = os.path.join(root_dir, entry)
            if os.path.isdir(full):
                for fname in sorted(os.listdir(full)):
                    if fname.lower().endswith(exts):
                        sid = os.path.splitext(fname)[0]
                        found.append((entry, sid, os.path.join(full, fname)))
            elif entry.lower().endswith(exts):
                sid = os.path.splitext(entry)[0]
                found.append(("cat", sid, full))
        return found

    def load_stickers(self):
        self._images.clear()
        for w in self.scroll.winfo_children():
            w.destroy()

        disk_items = self._collect_disk_stickers()
        entries = []

        if disk_items:
            for pack, sticker_id, img_path in disk_items:
                try:
                    with Image.open(img_path) as im:
                        pil_img = im.convert("RGBA").copy()
                    entries.append((pack, sticker_id, sticker_id, pil_img))
                except Exception:
                    pass

        if not entries:
            for pack, sticker_id, label, rgba in DEFAULT_STICKERS:
                entries.append(
                    (pack, sticker_id, label, _make_sticker_image(label, rgba))
                )

        col, row = 0, 0
        for pack, sticker_id, label, pil_img in entries:
            img = ctk.CTkImage(
                light_image=pil_img, dark_image=pil_img, size=(52, 52)
            )
            self._images.append(img)

            cell = ctk.CTkFrame(self.scroll, fg_color="#7C5DFA", corner_radius=10)
            cell.grid(row=row, column=col, padx=4, pady=4)

            btn = ctk.CTkButton(
                cell,
                image=img,
                text="",
                width=58,
                height=54,
                corner_radius=10,
                fg_color="#6A49FA",
                hover_color="#957BFA",
                command=lambda p=pack, sid=sticker_id: self._pick(p, sid),
            )
            btn.pack(padx=2, pady=(2, 0))

            lbl = ctk.CTkLabel(
                cell,
                text=label,
                font=("Segoe UI", 10, "bold"),
                text_color="#FFFFFF",
            )
            lbl.pack(pady=(0, 2))
            lbl.bind(
                "<Button-1>", lambda _e, p=pack, sid=sticker_id: self._pick(p, sid)
            )

            col += 1
            if col > 2:
                col = 0
                row += 1

    def _pick(self, pack: str, sticker_id: str):
        self.hide_popup()
        if callable(self.on_select_sticker_cb):
            self.on_select_sticker_cb(pack, sticker_id)

    def show_above_widget(self, anchor_widget=None):
        root = self.master
        if root is None:
            return
        self.load_stickers()
        pop_w, pop_h = 286, 246
        try:
            root.update_idletasks()
            win_w = max(400, int(root.winfo_width() or 1040))
            win_h = max(300, int(root.winfo_height() or 680))
            if anchor_widget is not None and anchor_widget.winfo_exists():
                anchor_widget.update_idletasks()
                ax = anchor_widget.winfo_rootx() - root.winfo_rootx()
                ay = anchor_widget.winfo_rooty() - root.winfo_rooty()
                x = max(16, min(ax, max(16, win_w - pop_w - 16)))
                y = ay - pop_h - 10
                if y < 16:
                    y = max(16, min(ay + 44, win_h - pop_h - 16))
            else:
                x = max(16, win_w - pop_w - 28)
                y = max(16, win_h - pop_h - 80)
        except Exception:
            x, y = 320, 360

        self.configure(width=pop_w, height=pop_h)
        self.place(x=x, y=y)
        self.update_idletasks()
        self.lift()
        self._is_open = True

    def toggle_above_widget(self, anchor_widget=None):
        if self._is_open and self.winfo_ismapped():
            self.hide_popup()
        else:
            self.show_above_widget(anchor_widget)

    def hide_popup(self):
        self._is_open = False
        try:
            if self.winfo_ismapped():
                self.place_forget()
        except Exception:
            pass