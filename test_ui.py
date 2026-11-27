import os
from PIL import Image
from ui.main_window import MainWindow


def ensure_sample_sticker():
    """Tạo sẵn 1 ảnh sticker mẫu nhỏ nếu thư mục assets/stickers chưa có ảnh."""
    sticker_dir = os.path.join("assets", "stickers", "cat")
    os.makedirs(sticker_dir, exist_ok=True)
    sample_path = os.path.join(sticker_dir, "cat_01.png")
    if not os.path.exists(sample_path):
        img = Image.new("RGBA", (128, 128), (106, 73, 250, 255))
        img.save(sample_path)


def main():
    ensure_sample_sticker()
    app = MainWindow(enable_local_preview=True)
    app.mainloop()


if __name__ == "__main__":
    main()