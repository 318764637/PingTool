import customtkinter as ctk
from ...core.firewall import STATE_TEXT, STATE_UNKNOWN
from ..styles import COLORS, FONTS, SIZES


class FirewallCard(ctk.CTkFrame):
    """Windows 防火墙卡片：一键关闭 / 恢复开启 / 刷新状态。

    三个动作都通过 on_action(action) 回调上抛，由主窗口在后台线程执行，
    卡片自身只负责按钮状态与状态文案。
    """

    # 状态文案与 core.firewall 共用一份，避免两处维护
    _STATE_COLOR = {
        "on": "success",
        "off": "error",
        "partial": "warning",
        "unknown": "text_dim",
    }

    def __init__(self, master, on_action, **kwargs):
        super().__init__(master, fg_color=COLORS["card_bg"],
                         corner_radius=SIZES["card_corner_radius"], **kwargs)
        self._on_action = on_action

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(self, text="Windows 防火墙", font=FONTS["subtitle"],
                             text_color=COLORS["text"])
        title.grid(row=0, column=0, columnspan=2, sticky="w",
                   padx=SIZES["card_padding"], pady=(10, 2))

        self._state_label = ctk.CTkLabel(self, text="状态: 读取中...",
                                         font=FONTS["body"], text_color=COLORS["text_dim"])
        self._state_label.grid(row=1, column=0, columnspan=2, sticky="w",
                               padx=SIZES["card_padding"], pady=(0, 2))

        self._detail_label = ctk.CTkLabel(self, text="", font=FONTS["small"],
                                          text_color=COLORS["text_dim"], anchor="w",
                                          justify="left", wraplength=420)
        self._detail_label.grid(row=2, column=0, columnspan=2, sticky="ew",
                                padx=SIZES["card_padding"], pady=(0, 6))

        self._off_btn = ctk.CTkButton(
            self, text="一键关闭防火墙", font=FONTS["body"],
            fg_color=COLORS["error"], hover_color="#d32f2f",
            corner_radius=SIZES["button_corner_radius"],
            command=lambda: self._on_action("off"),
        )
        self._off_btn.grid(row=3, column=0, sticky="ew",
                           padx=(SIZES["card_padding"], 5), pady=(0, 10))

        self._on_btn = ctk.CTkButton(
            self, text="恢复开启", font=FONTS["body"],
            fg_color=COLORS["success"], hover_color="#45a049",
            corner_radius=SIZES["button_corner_radius"],
            command=lambda: self._on_action("on"),
        )
        self._on_btn.grid(row=3, column=1, sticky="ew",
                          padx=(5, 5), pady=(0, 10))

        self._refresh_btn = ctk.CTkButton(
            self, text="刷新", width=56, font=FONTS["small"],
            fg_color="transparent", hover_color=COLORS["border"],
            text_color=COLORS["text_dim"],
            corner_radius=SIZES["button_corner_radius"],
            command=lambda: self._on_action("refresh"),
        )
        self._refresh_btn.grid(row=3, column=2, padx=(0, SIZES["card_padding"]),
                               pady=(0, 10))

        self._state = None
        self._detail = ""

    def set_busy(self, busy, action=None):
        """操作期间禁用按钮并给出进行中文案。"""
        if busy:
            # 刷新时按钮文案保持不变，仅置灰，避免与开关动作混淆
            label = {"off": "关闭中...", "on": "开启中..."}
            self._off_btn.configure(state="disabled",
                                    text=label.get(action, "一键关闭防火墙"))
            self._on_btn.configure(state="disabled", text="恢复开启")
            self._refresh_btn.configure(state="disabled")
        else:
            self._off_btn.configure(state="normal", text="一键关闭防火墙")
            self._on_btn.configure(state="normal", text="恢复开启")
            self._refresh_btn.configure(state="normal")

    def update_state(self, state, detail=""):
        """按状态更新文案与颜色；detail 为附加说明（可空）。"""
        text = STATE_TEXT.get(state, STATE_TEXT[STATE_UNKNOWN])
        color_key = self._STATE_COLOR.get(state, "text_dim")
        self._state = state
        self._state_label.configure(text=f"状态: {text}", text_color=COLORS[color_key])
        if detail != self._detail:
            self._detail = detail
            self._detail_label.configure(text=detail)
