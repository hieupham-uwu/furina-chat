import os
import customtkinter as ctk
from PIL import Image
import config


def _get_stickers_dir() -> str:
    val = getattr(config, "STICKERS_DIR", None)
    if val:
        return val
    assets_dir = getattr(config, "ASSETS_DIR", None)
    if assets_dir:
        return os.path.join(assets_dir, "stickers")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets", "stickers")


class StickerPopup(ctk.CTkFrame):
    """Ô sticker nhỏ nổi ngay phía trên khung nhập (giống Messenger/Zalo), không mở cửa sổ mới."""

    def __init__(self, master, on_select_sticker_cb, **kwargs):
        super().__init__(
            master,
            width=284,
            height=212,
            corner_radius=16,
            border_width=1,
            border_color="#C6E6FF",
            fg_color="#FFFFFF",
            **kwargs,
        )
        self.on_select_sticker_cb = on_select_sticker_cb
        self._sticker_images = []

        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=28)
        top_bar.pack(fill="x", padx=10, pady=(6, 2))

        title = ctk.CTkLabel(
            top_bar,
            text="Sticker",
            font=("Segoe UI", 12, "bold"),
            text_color="#453284",
        )
        title.pack(side="left")

        close_btn = ctk.CTkButton(
            top_bar,
            text="✕",
            width=22,
            height=22,
            corner_radius=11,
            fg_color="transparent",
            hover_color="#C6E6FF",
            text_color="#453284",
            command=self.hide_popup,
        )
        close_btn.pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#F5F3FF",
            corner_radius=12,
        )
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        self.reload_stickers()

    def reload_stickers(self):
        self._sticker_images.clear()
        for w in self.scroll.winfo_children():
            w.destroy()

        stickers_root = _get_stickers_dir()
        if not os.path.exists(stickers_root):
            ctk.CTkLabel(
                self.scroll,
                text="Chưa có thư mục stickers",
                font=("Segoe UI", 11),
                text_color="#6B7280",
            ).pack(pady=16)
            return

        items = []
        for entry in sorted(os.listdir(stickers_root)):
            full_entry = os.path.join(stickers_root, entry)
            if os.path.isdir(full_entry):
                for fname in sorted(os.listdir(full_entry)):
                    if fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        sid = os.path.splitext(fname)[0]
                        items.append((entry, sid, os.path.join(full_entry, fname)))
            elif entry.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                sid = os.path.splitext(entry)[0]
                items.append(("default", sid, full_entry))

        if not items:
            ctk.CTkLabel(
                self.scroll,
                text="Chưa có sticker nào",
                font=("Segoe UI", 11),
                text_color="#6B7280",
            ).pack(pady=16)
            return

        col = 0
        row = 0
        for pack, sticker_id, full_path in items:
            try:
                with Image.open(full_path) as im:
                    pil_img = im.copy()
                ctk_img = ctk.CTkImage(
                    light_image=pil_img, dark_image=pil_img, size=(52, 52)
                )
                self._sticker_images.append(ctk_img)

                btn = ctk.CTkButton(
                    self.scroll,
                    image=ctk_img,
                    text="",
                    width=56,
                    height=56,
                    corner_radius=10,
                    fg_color="transparent",
                    hover_color="#C6E6FF",
                    command=lambda p=pack, s=sticker_id: self._select(p, s),
                )
                btn.grid(row=row, column=col, padx=4, pady=4)
                col += 1
                if col >= 4:
                    col = 0
                    row += 1
            except Exception as e:
                print(f"Lỗi load sticker {full_path}: {e}")

    def _select(self, pack: str, sticker_id: str):
        self.hide_popup()
        if self.on_select_sticker_cb:
            self.on_select_sticker_cb(pack, sticker_id)

    def toggle(self, x: int, y: int):
        if self.winfo_ismapped():
            self.hide_popup()
        else:
            self.reload_stickers()
            self.place(x=x, y=y)
            self.lift()

    def hide_popup(self):
        if self.winfo_ismapped():
            self.place_forget()