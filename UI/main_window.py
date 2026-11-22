import customtkinter as ctk
import threading
import time
from ui.peer_sidebar import PeerSidebar
from ui.chat_panel import ChatPanel

ctk.set_appearance_mode("Light")

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Furina Chat")
        self.geometry("950x650")
        self.configure(fg_color="#F4F6FB")

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = PeerSidebar(self)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(15, 10), pady=15)
        
        self.chat_area = ChatPanel(self)
        self.chat_area.grid(row=0, column=1, sticky="nsew", padx=(0, 15), pady=15)

        # Bắt đầu luồng giả lập sự kiện
        self.simulate_network_event()

    def simulate_network_event(self):
        # Hàm này chạy ngầm, đợi 2 giây rồi đẩy tin nhắn lên GUI
        def run():
            time.sleep(2) # Đợi 2 giây
            # Đẩy tin nhắn vào khung chat (giả lập nhận được từ mạng)
            self.chat_area.chat_display.configure(state="normal")
            self.chat_area.chat_display.insert("end", "MAnh (Giả lập): Chào Minh Anh, đây là sự kiện từ mạng!\n\n")
            self.chat_area.chat_display.configure(state="disabled")
        threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()