import customtkinter as ctk
from ..styles import COLORS, FONTS, SIZES


class TailscaleCard(ctk.CTkFrame):
    def __init__(self, master, on_restart, **kwargs):
        super().__init__(master, fg_color=COLORS["card_bg"], corner_radius=SIZES["card_corner_radius"], **kwargs)
        self._on_restart = on_restart

        self.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(self, text="Tailscale 服务", font=FONTS["subtitle"], text_color=COLORS["text"])
        title.grid(row=0, column=0, columnspan=2, sticky="w", padx=SIZES["card_padding"], pady=(10, 5))

        self._status_label = ctk.CTkLabel(self, text="状态: 未知", font=FONTS["body"], text_color=COLORS["text_dim"])
        self._status_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=SIZES["card_padding"], pady=(0, 10))

        self._restart_btn = ctk.CTkButton(
            self, text="重启服务", font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["info"],
            corner_radius=SIZES["button_corner_radius"],
            command=lambda: self._on_restart(),
        )
        self._restart_btn.grid(row=2, column=0, columnspan=2, padx=SIZES["card_padding"], pady=(0, 10))

    def set_busy(self, busy):
        """操作期间禁用按钮；由主窗口在「确认之后」调用，避免取消确认后按钮卡住。"""
        if busy:
            self._restart_btn.configure(state="disabled", text="重启中...")
        else:
            self._restart_btn.configure(state="normal", text="重启服务")

    def update_status(self, success, message):
        self.set_busy(False)
        if success:
            self._status_label.configure(text=f"状态: {message}", text_color=COLORS["success"])
        else:
            self._status_label.configure(text=f"状态: {message}", text_color=COLORS["error"])

    def set_status_text(self, text, color=None):
        if color is None:
            color = COLORS["text_dim"]
        self._status_label.configure(text=f"状态: {text}", text_color=color)
