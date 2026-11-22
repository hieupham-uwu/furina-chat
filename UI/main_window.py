import customtkinter as ctk

# Cấu hình giao diện chung
ctk.set_appearance_mode("Light") # Chuyển sang nền sáng
ctk.set_default_color_theme("blue")

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Furina Chat")
        self.geometry("950x650")
        self.configure(fg_color="#F4F6FB") # Màu nền tổng thể (trắng hơi ngả xanh nhạt)

        # Chia cột: Cột 0 (Sidebar) - Cột 1 (Chat)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ================= CỘT TRÁI: SIDEBAR =================
        # Nền sidebar màu trắng, bo góc trên phải và dưới phải
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=20, fg_color="white")
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(15, 10), pady=15)
        
        # Tiêu đề Sidebar
        ctk.CTkLabel(self.sidebar, text="Chats", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color="#453284").pack(pady=(20, 10), padx=20, anchor="w")

        # Ô tìm kiếm (Giả lập)
        self.search_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Search...", corner_radius=20, fg_color="#C6E6FF", text_color="#453284", border_width=0)
        self.search_entry.pack(pady=(0, 20), padx=20, fill="x")

        # Danh sách bạn bè (Các "Thẻ" - Card)
        peers = [
            {"name": "Hiếu", "status": "Online", "color": "#6A49FA"},
            {"name": "Dương", "status": "Away", "color": "#FEDADA"},
            {"name": "Minh Anh", "status": "Online", "color": "#6A49FA"}
        ]
        
        for peer in peers:
            # Khung chứa từng người bạn
            card = ctk.CTkFrame(self.sidebar, fg_color="#F4F6FB", corner_radius=15)
            card.pack(pady=5, padx=15, fill="x")
            
            # Avatar tròn (Giả lập bằng label màu)
            avatar = ctk.CTkLabel(card, text="", width=40, height=40, corner_radius=20, fg_color=peer["color"])
            avatar.pack(side="left", padx=15, pady=10)
            
            # Tên và trạng thái
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True)
            ctk.CTkLabel(info_frame, text=peer["name"], font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color="#453284").pack(anchor="w", pady=(5, 0))
            ctk.CTkLabel(info_frame, text=peer["status"], font=ctk.CTkFont(family="Segoe UI", size=12), text_color="gray").pack(anchor="w", pady=(0, 5))

        # Nút đổi trạng thái (Ghim ở dưới cùng)
        self.status_btn = ctk.CTkButton(self.sidebar, text="Đổi trạng thái", fg_color="#6A49FA", hover_color="#453284", corner_radius=20, font=ctk.CTkFont(weight="bold"))
        self.status_btn.pack(side="bottom", pady=20, padx=20, fill="x")


        # ================= CỘT PHẢI: KHUNG CHAT =================
        self.chat_area = ctk.CTkFrame(self, fg_color="transparent")
        self.chat_area.grid(row=0, column=1, sticky="nsew", padx=(0, 15), pady=15)
        self.chat_area.grid_rowconfigure(0, weight=1)
        self.chat_area.grid_columnconfigure(0, weight=1)

        # Khung hiển thị tin nhắn (Nền trắng, bo góc)
        self.chat_display = ctk.CTkTextbox(self.chat_area, font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 15))
        
        # Chèn đoạn chat mẫu
        self.chat_display.insert("end", "Hệ thống: Chào mừng Hiếu đến với giao diện mới!\n\n")
        self.chat_display.insert("end", "Hiếu:  💜\n\n")
        self.chat_display.configure(state="disabled") 

        # Thanh nhập tin nhắn (Nằm dưới cùng)
        self.input_frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        # Ô nhập chữ
        self.msg_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Nhập tin nhắn...", font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=25, border_width=2, border_color="#C6E6FF")
        self.msg_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=8)

        # Nút gửi (Tròn, màu tím)
        self.send_btn = ctk.CTkButton(self.input_frame, text="Gửi", width=90, height=40, corner_radius=20, fg_color="#6A49FA", hover_color="#453284", font=ctk.CTkFont(weight="bold"), command=self.send_msg)
        self.send_btn.grid(row=0, column=1)

    def send_msg(self):
        msg = self.msg_entry.get()
        if msg:
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"Bạn: {msg}\n\n")
            self.chat_display.configure(state="disabled")
            self.msg_entry.delete(0, "end")

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()