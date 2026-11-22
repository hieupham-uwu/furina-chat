import customtkinter as ctk
from tkinter import filedialog
import os
from PIL import Image

class ChatPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- KHUNG HIỂN THỊ TIN NHẮN ---
        self.chat_display = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 15))
        self.chat_display.insert("end", "Hệ thống: Chào mừng Minh Anh!\n\n")
        self.chat_display.configure(state="disabled")

        # --- KHUNG NHẬP LIỆU ---
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.toolbar_frame = ctk.CTkFrame(self.bottom_frame, fg_color="white", corner_radius=20)
        self.toolbar_frame.pack(side="left", fill="y", padx=(0, 10))

        self.attach_btn = ctk.CTkButton(self.toolbar_frame, text="📎", width=35, height=35, fg_color="transparent", text_color="#6A49FA", hover_color="#C6E6FF", font=("Segoe UI Emoji", 20), command=self.choose_file)
        self.attach_btn.pack(side="left", padx=2, pady=2)

        self.image_btn = ctk.CTkButton(self.toolbar_frame, text="🖼️", width=35, height=35, fg_color="transparent", text_color="#6A49FA", hover_color="#C6E6FF", font=("Segoe UI Emoji", 20), command=self.choose_image)
        self.image_btn.pack(side="left", padx=2, pady=2)

        self.sticker_btn = ctk.CTkButton(self.toolbar_frame, text="😀", width=35, height=35, fg_color="transparent", text_color="#6A49FA", hover_color="#C6E6FF", font=("Segoe UI Emoji", 20), command=self.toggle_sticker_panel)
        self.sticker_btn.pack(side="left", padx=2, pady=2)

        self.msg_entry = ctk.CTkEntry(self.bottom_frame, placeholder_text="Aa", font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=20, border_width=0)
        self.msg_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 10))
        self.msg_entry.bind("<Return>", lambda event: self.send_msg())

        self.send_btn = ctk.CTkButton(self.bottom_frame, text="➤", width=40, height=40, corner_radius=20, fg_color="#6A49FA", hover_color="#453284", font=("Segoe UI", 18, "bold"), command=self.send_msg)
        self.send_btn.pack(side="right")

        # --- BẢNG CHỌN STICKER (ẨN LÚC ĐẦU) ---
        # Sử dụng place để nó nổi lên trên thanh nhập liệu
        self.sticker_panel = ctk.CTkFrame(self, fg_color="white", corner_radius=10, border_width=1, border_color="#C6E6FF")
        
        # Nút tắt bảng sticker
        self.close_sticker_btn = ctk.CTkButton(self.sticker_panel, text="✖", width=25, height=25, fg_color="transparent", text_color="gray", hover_color="#FEDADA", command=self.hide_sticker_panel)
        self.close_sticker_btn.pack(anchor="ne", padx=5, pady=5)

        self.sticker_list_frame = ctk.CTkScrollableFrame(self.sticker_panel, fg_color="transparent", width=300, height=150)
        self.sticker_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.load_stickers_to_panel()
        self.sticker_panel_visible = False # Trạng thái ban đầu là ẩn

    def load_stickers_to_panel(self):
        sticker_dir = os.path.join("assets", "stickers")
        if os.path.exists(sticker_dir):
            files = [f for f in os.listdir(sticker_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]
            if not files:
                ctk.CTkLabel(self.sticker_list_frame, text="Thư mục stickers trống!").pack()
            else:
                for file in files:
                    img_path = os.path.join(sticker_dir, file)
                    pil_img = Image.open(img_path)
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(40, 40))
                    
                    btn = ctk.CTkButton(self.sticker_list_frame, image=ctk_img, text="", width=45, height=45, fg_color="transparent", hover_color="#C6E6FF", command=lambda f=img_path: self.select_sticker(f))
                    btn.pack(side="left", padx=5, pady=5)
        else:
            ctk.CTkLabel(self.sticker_list_frame, text="Không tìm thấy thư mục assets/stickers").pack()

    def toggle_sticker_panel(self):
        if self.sticker_panel_visible:
            self.hide_sticker_panel()
        else:
            # Hiển thị bảng ngay phía trên thanh nhập liệu (cách đáy 70px)
            # relativex=0.5, anchor="s" (hướng nam) để nó canh giữa thanh nhập
            self.sticker_panel.place(relx=0.5, rely=1.0, y=-70, anchor="s")
            self.sticker_panel.lift() # Đảm bảo nó nằm trên cùng
            self.sticker_panel_visible = True

    def hide_sticker_panel(self):
        self.sticker_panel.place_forget() # Ẩn khung đi
        self.sticker_panel_visible = False

    def send_msg(self):
        msg = self.msg_entry.get()
        if msg.strip():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"Bạn: {msg}\n\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")
            self.msg_entry.delete(0, "end")
            self.hide_sticker_panel() # Gõ tin nhắn thì tự động ẩn bảng sticker

    def choose_file(self):
        filepath = filedialog.askopenfilename(title="Chọn file để gửi")
        if filepath:
            filename = os.path.basename(filepath)
            self.display_system_msg(f"Bạn đã chọn file: {filename}")

    def choose_image(self):
        filepath = filedialog.askopenfilename(title="Chọn ảnh để gửi", filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
        if filepath:
            filename = os.path.basename(filepath)
            self.display_system_msg(f"Bạn đã chọn ảnh: {filename}")

    def select_sticker(self, img_path):
        # Load ảnh
        pil_img = Image.open(img_path)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(100, 100))
        
        # Khởi tạo list chứa ảnh nếu chưa có
        if not hasattr(self, 'image_references'):
            self.image_references = []
        
        # Mở khóa khung chat để chèn
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", "Bạn: ")
        
        # Chèn ảnh và LƯU Ý DÒNG NÀY: Gán window/ảnh vào biến cục bộ để Textbox giữ nó
        self.chat_display.image_create("end", image=ctk_img, padx=10, pady=10)
        
        self.chat_display.insert("end", "\n\n")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")
        
        # Lưu ảnh vào list để chống mất
        self.image_references.append(ctk_img)
        
        self.hide_sticker_panel()

    def display_system_msg(self, text):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"Hệ thống: {text}\n\n")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")