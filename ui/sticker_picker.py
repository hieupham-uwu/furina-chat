import os
import customtkinter as ctk
from PIL import Image, ImageDraw
import config

DEFAULT_STICKERS = [
    ("cat", "hello", "Hello", (106, 73, 250, 255)),
    ("cat", "love", "Love", (236, 72, 153, 255)),
    ("cat", "laugh", "Haha", (234, 179, 8, 255)),
    ("cat", "ok", "OK", (22, 163, 74, 255)),
    ("cat", "sad", "Sad", (59, 130, 246, 255)),
    ("cat", "wow", "Wow", (249, 115, 22, 255)),
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
    draw.text((12, 24), text, fill=(255, 255, 255, 255))
    return img


class StickerPicker(ctk.CTkToplevel):
    """Cửa sổ nổi chọn sticker: luôn mở phía trên cửa sổ ứng dụng."""

    def __init__(self, master, on_sticker_selected, anchor_widget=None, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Chọn Sticker")
        self.geometry("310x250")
        self.resizable(False, False)
        self.configure(fg_color="#F5F3FF")
        self.on_sticker_selected = on_sticker_selected
        self._images = []

        if master is not None:
            try:
                self.transient(master)
            except Exception:
                pass
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        self._position_near_anchor(anchor_widget, master)

        header = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=12, height=34)
        header.pack(fill="x", padx=8, pady=(8, 4))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="Chọn sticker để gửi",
            font=("Segoe UI", 12, "bold"),
            text_color="#453284",
        ).pack(side="left", padx=10)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#FFFFFF",
            corner_radius=12,
        )
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.load_stickers()
        self.after(10, self._bring_to_front)

    def _bring_to_front(self):
        try:
            if self.winfo_exists():
                self.lift()
                self.attributes("-topmost", True)
                self.focus_force()
        except Exception:
            pass

    def _position_near_anchor(self, anchor_widget, master=None):
        try:
            self.update_idletasks()
            if anchor_widget is not None and anchor_widget.winfo_exists():
                anchor_widget.update_idletasks()
                ax = anchor_widget.winfo_rootx()
                ay = anchor_widget.winfo_rooty()
                x = max(20, ax)
                y = max(20, ay - 260)
                self.geometry(f"310x250+{x}+{y}")
            elif master is not None and master.winfo_exists():
                mx = master.winfo_rootx() + max(40, master.winfo_width() - 360)
                my = master.winfo_rooty() + max(40, master.winfo_height() - 330)
                self.geometry(f"310x250+{mx}+{my}")
        except Exception:
            pass

    def _collect_sticker_files(self):
        stickers_root = _get_stickers_dir()
        if not os.path.isdir(stickers_root):
            return []

        exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        items = []

        for entry in sorted(os.listdir(stickers_root)):
            full = os.path.join(stickers_root, entry)
            if os.path.isdir(full):
                for fname in sorted(os.listdir(full)):
                    if fname.lower().endswith(exts):
                        sid = os.path.splitext(fname)[0]
                        items.append((entry, sid, os.path.join(full, fname)))
            elif entry.lower().endswith(exts):
                sid = os.path.splitext(entry)[0]
                items.append(("cat", sid, full))

        return items

    def load_stickers(self):
        self._images.clear()
        for child in self.scroll.winfo_children():
            child.destroy()

        disk_items = self._collect_sticker_files()
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
                light_image=pil_img, dark_image=pil_img, size=(56, 56)
            )
            self._images.append(img)

            btn = ctk.CTkButton(
                self.scroll,
                image=img,
                text="",
                width=62,
                height=62,
                corner_radius=12,
                fg_color="transparent",
                hover_color="#EDE9FE",
                command=lambda p=pack, sid=sticker_id: self.select_sticker(p, sid),
            )
            btn.grid(row=row, column=col, padx=5, pady=5)

            col += 1
            if col > 3:
                col = 0
                row += 1

    def select_sticker(self, pack, sticker_id):
        cb = self.on_sticker_selected
        try:
            self.destroy()
        except Exception:
            pass
        if callable(cb):
            cb(pack, sticker_id)