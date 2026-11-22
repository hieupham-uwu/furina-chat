import customtkinter as ctk

class PeerSidebar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, width=280, corner_radius=20, fg_color="white")
        
        ctk.CTkLabel(self, text="Chats", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color="#453284").pack(pady=(20, 10), padx=20, anchor="w")
        
        self.search_entry = ctk.CTkEntry(self, placeholder_text="Search...", corner_radius=20, fg_color="#C6E6FF", text_color="#453284", border_width=0)
        self.search_entry.pack(pady=(0, 20), padx=20, fill="x")

        # Nút đổi trạng thái (Ghim ở dưới cùng)
        self.status_btn = ctk.CTkButton(self, text="Đổi trạng thái", fg_color="#6A49FA", hover_color="#453284", corner_radius=20)
        self.status_btn.pack(side="bottom", pady=20, padx=20, fill="x")