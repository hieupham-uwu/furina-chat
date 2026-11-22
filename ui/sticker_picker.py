import customtkinter as ctk
import os
from PIL import Image

class StickerPicker(ctk.CTkToplevel):
    def __init__(self, parent, on_sticker_selected):
        super().__init__(parent)
        self.title("Chọn Sticker")
        self.geometry("300x150")
        self.on_sticker_selected = on_sticker_selected
        
        # Đảm bảo cửa sổ này luôn nằm trên cửa sổ chính
        self.attributes("-topmost", True)
        
        # Tìm thư mục chứa sticker
        sticker_dir = os.path.join("assets", "stickers")
        
        # Tạo khung chứa các nút
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=10, pady=10)

        # Đọc các file ảnh trong thư mục
        if os.path.exists(sticker_dir):
            files = [f for f in os.listdir(sticker_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]
            
            if not files:
                ctk.CTkLabel(frame, text="Chưa có ảnh trong thư mục assets/stickers/").pack()
            else:
                for file in files:
                    # Load ảnh bằng Pillow và resize cho nhỏ lại
                    img_path = os.path.join(sticker_dir, file)
                    pil_img = Image.open(img_path)
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(40, 40))
                    
                    # Tạo nút bấm chứa ảnh
                    btn = ctk.CTkButton(frame, image=ctk_img, text="", width=50, height=50, fg_color="transparent", hover_color="#C6E6FF", command=lambda f=img_path: self.select_sticker(f))
                    btn.pack(side="left", padx=5)
        else:
            ctk.CTkLabel(frame, text="Không tìm thấy thư mục assets/stickers").pack()

    def select_sticker(self, img_path):
        # Gửi đường dẫn ảnh về cho cửa sổ chat
        self.on_sticker_selected(img_path)
        self.destroy() # Đóng cửa sổ chọn