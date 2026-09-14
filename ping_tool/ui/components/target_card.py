import tkinter as tk
import customtkinter as ctk

from ..styles import COLORS, FONTS, SIZES


class TargetCard(ctk.CTkFrame):
    """单个 Ping 目标卡片。

    高频刷新的文本（状态点 / 延迟 / 平均）使用原生 tk.Label：
    CustomTkinter 控件每次 configure 都会重绘整块画布（圆角矩形+阴影+文字），
    而 tk.Label 是原生控件，文本/颜色更新开销低 1~2 个数量级，
    是多目标高频刷新下消除 UI 卡顿的关键。控件背景色与卡片填充色一致，视觉无差异。
    """

    def __init__(self, master, target, on_delete, **kwargs):
        super().__init__(master, fg_color=COLORS["card_bg"], corner_radius=SIZES["card_corner_radius"], **kwargs)
        self._target = target
        self._on_delete = on_delete

        self.grid_columnconfigure(1, weight=1)
        bg = COLORS["card_bg"]  # 与卡片画布填充色一致，保证原生控件无缝贴合

        self._status_dot = tk.Label(
            self, text="●", width=2,
            font=FONTS["body"], fg=COLORS["text_dim"], bg=bg,
        )
        self._status_dot.grid(row=0, column=0, padx=(10, 5), pady=8)

        self._target_label = tk.Label(
            self, text=target,
            font=FONTS["body"], fg=COLORS["text"], bg=bg, anchor="w",
        )
        self._target_label.grid(row=0, column=1, sticky="ew", padx=5, pady=8)

        self._latency_label = tk.Label(
            self, text="-- ms", width=8,
            font=FONTS["mono"], fg=COLORS["text_dim"], bg=bg,
        )
        self._latency_label.grid(row=0, column=2, padx=5, pady=8)

        self._avg_label = tk.Label(
            self, text="avg: --", width=10,
            font=FONTS["small"], fg=COLORS["text_dim"], bg=bg,
        )
        self._avg_label.grid(row=0, column=3, padx=5, pady=8)

        self._delete_btn = ctk.CTkButton(
            self, text="×", width=28, height=28,
            fg_color="transparent", hover_color=COLORS["error"],
            text_color=COLORS["text_dim"], font=FONTS["body"],
            command=self._handle_delete,
        )
        self._delete_btn.grid(row=0, column=4, padx=(5, 10), pady=8)

        # 上次渲染状态缓存：值未变化时跳过 configure，避免无效重绘
        self._dot_color = COLORS["text_dim"]
        self._latency_state = ("-- ms", COLORS["text_dim"])
        self._avg_text = "avg: --"

    def _handle_delete(self):
        self._on_delete(self._target)

    def _set_dot_color(self, color):
        if color != self._dot_color:
            self._dot_color = color
            self._status_dot.configure(fg=color)

    def _set_latency(self, text, color):
        state = (text, color)
        if state != self._latency_state:
            self._latency_state = state
            self._latency_label.configure(text=text, fg=color)

    def _set_avg(self, text):
        if text != self._avg_text:
            self._avg_text = text
            self._avg_label.configure(text=text)

    def update_status(self, result):
        if result.get("timeout"):
            self._set_dot_color(COLORS["error"])
            self._set_latency("超时", COLORS["error"])
            self._set_avg("avg: --")
        else:
            latency = result.get("latency")
            avg = result.get("avg")
            self._set_dot_color(COLORS["success"])
            # 延迟分级与设计规范一致：<30 绿 / <80 蓝 / <150 琥珀 / >=150 红
            if latency < 30:
                color = COLORS["success"]
            elif latency < 80:
                color = COLORS["info"]
            elif latency < 150:
                color = COLORS["warning"]
            else:
                color = COLORS["error"]
            self._set_latency(f"{latency} ms", color)
            self._set_avg(f"avg: {avg}" if avg is not None else "avg: --")

    def reset(self):
        self._set_dot_color(COLORS["text_dim"])
        self._set_latency("-- ms", COLORS["text_dim"])
        self._set_avg("avg: --")
