import customtkinter as ctk

class ChatPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Khung hiển thị tin nhắn
        self.chat_display = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 15))
        self.chat_display.insert("end", "Hệ thống: Chào mừng Minh Anh!\n\n")
        self.chat_display.configure(state="disabled")

        # Thanh nhập tin nhắn
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Nhập tin nhắn...", font=ctk.CTkFont(family="Segoe UI", size=15), fg_color="white", text_color="#453284", corner_radius=25, border_width=2, border_color="#C6E6FF")
        self.msg_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=8)

        self.send_btn = ctk.CTkButton(self.input_frame, text="Gửi", width=90, height=40, corner_radius=20, fg_color="#6A49FA", hover_color="#453284", command=self.send_msg)
        self.send_btn.grid(row=0, column=1)

    def send_msg(self):
        msg = self.msg_entry.get()
        if msg:
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"Bạn: {msg}\n\n")
            self.chat_display.configure(state="disabled")
            self.msg_entry.delete(0, "end")