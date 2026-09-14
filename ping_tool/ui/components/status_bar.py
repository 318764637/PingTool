import customtkinter as ctk
from ..styles import COLORS, FONTS


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(self, text="就绪", font=FONTS["small"], text_color=COLORS["text_dim"])
        self._status_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self._count_label = ctk.CTkLabel(self, text="目标: 0", font=FONTS["small"], text_color=COLORS["text_dim"])
        self._count_label.grid(row=0, column=1, sticky="e", padx=10, pady=5)

        # 上次渲染状态缓存：值未变化时跳过 configure
        self._status_state = None
        self._count_text = None

    def set_status(self, text, color=None):
        if color is None:
            color = COLORS["text_dim"]
        state = (text, color)
        if state == self._status_state:
            return
        self._status_state = state
        self._status_label.configure(text=text, text_color=color)

    def set_count(self, count, pinging=0):
        if pinging > 0:
            text = f"目标: {count} | Ping中: {pinging}"
        else:
            text = f"目标: {count}"
        if text == self._count_text:
            return
        self._count_text = text
        self._count_label.configure(text=text)
