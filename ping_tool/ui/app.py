import customtkinter as ctk
import atexit
import queue
import threading
import time
from tkinter import messagebox
from ..config import get_config
from ..logger import get_logger
from ..data.manager import DataManager
from ..core.ping_worker import PingWorker
from ..core.tailscale import TailscaleManager
from ..core.firewall import FirewallManager
from ..utils.validators import validate_target, sanitize_target
from .styles import COLORS, FONTS, SIZES, WINDOW
from .components.target_card import TargetCard
from .components.tailscale_card import TailscaleCard
from .components.firewall_card import FirewallCard
from .components.status_bar import StatusBar

logger = get_logger(__name__)


class PingApp(ctk.CTk):
    # 主线程结果轮询间隔（毫秒）。
    # 所有 worker 结果先入队，主线程按此节奏批量刷新 UI：
    # - 避免每个结果单独 after(0) 造成主线程回调风暴（CustomTkinter 重绘昂贵）；
    # - 突发结果被合并为一次刷新，天然限频。
    _POLL_INTERVAL_MS = 100

    def __init__(self):
        super().__init__()
        self._config = get_config()
        self._data_manager = DataManager()
        self._tailscale = TailscaleManager()
        self._firewall = FirewallManager()
        self._workers = {}
        self._cards = {}
        # 卡片行号只增不减：删除中间目标后若按 len(_cards) 取行号，
        # 新卡片会与仍占用旧行号的卡片重叠
        self._next_row = 0
        self._is_pinging = False
        self._closing = False
        self._result_queue = queue.Queue()
        # 后台线程 → 主线程的控制类结果（Tailscale / 防火墙），与 Ping 结果分开
        self._control_queue = queue.Queue()

        self._setup_window()
        self._create_ui()
        self._load_targets()
        self._refresh_firewall_state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        atexit.register(self._cleanup_on_exit)
        self._schedule_ui_poll()

    def _setup_window(self):
        width = self._config.get("window_width", WINDOW["width"])
        height = self._config.get("window_height", WINDOW["height"])
        self.title("Ping Tool")
        self.geometry(f"{width}x{height}")
        self.minsize(WINDOW["min_width"], WINDOW["min_height"])
        self.configure(fg_color=COLORS["bg"])
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    def _create_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._create_input_area()
        self._create_button_area()
        self._create_scroll_area()
        self._create_tailscale_area()
        self._create_firewall_area()
        self._create_status_bar()

    def _create_input_area(self):
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=0, column=0, sticky="ew", padx=SIZES["padding"], pady=(SIZES["padding"], 5))
        input_frame.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            input_frame, placeholder_text="输入 IP 或域名",
            font=FONTS["body"], corner_radius=SIZES["entry_corner_radius"],
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._entry.bind("<Return>", lambda e: self._add_target())

        self._add_btn = ctk.CTkButton(
            input_frame, text="添加", width=60, font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["info"],
            corner_radius=SIZES["button_corner_radius"],
            command=self._add_target,
        )
        self._add_btn.grid(row=0, column=1)

    def _create_button_area(self):
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=SIZES["padding"], pady=5)

        self._start_btn = ctk.CTkButton(
            btn_frame, text="全部开始", font=FONTS["body"],
            fg_color=COLORS["success"], hover_color="#45a049",
            corner_radius=SIZES["button_corner_radius"],
            command=self._start_all,
        )
        self._start_btn.grid(row=0, column=0, padx=(0, 10))

        self._stop_btn = ctk.CTkButton(
            btn_frame, text="全部停止", font=FONTS["body"],
            fg_color=COLORS["error"], hover_color="#d32f2f",
            corner_radius=SIZES["button_corner_radius"],
            command=self._stop_all, state="disabled",
        )
        self._stop_btn.grid(row=0, column=1, padx=(0, 10))

    def _create_scroll_area(self):
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            label_text="Ping 目标", label_font=FONTS["subtitle"],
            label_fg_color=COLORS["bg"],
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew", padx=SIZES["padding"], pady=5)
        self._scroll_frame.grid_columnconfigure(0, weight=1)

    def _create_tailscale_area(self):
        self._tailscale_card = TailscaleCard(self, on_restart=self._restart_tailscale)
        self._tailscale_card.grid(row=3, column=0, sticky="ew", padx=SIZES["padding"], pady=5)

    def _create_firewall_area(self):
        self._firewall_card = FirewallCard(self, on_action=self._firewall_action)
        self._firewall_card.grid(row=4, column=0, sticky="ew", padx=SIZES["padding"], pady=5)

    def _create_status_bar(self):
        self._status_bar = StatusBar(self)
        self._status_bar.grid(row=5, column=0, sticky="ew", padx=SIZES["padding"], pady=(5, SIZES["padding"]))

    def _load_targets(self):
        targets = self._data_manager.load()
        for target in targets:
            self._add_card(target)
        self._update_count()

    def _add_target(self):
        target = sanitize_target(self._entry.get())
        if not target:
            return

        valid, msg = validate_target(target)
        if not valid:
            self._status_bar.set_status(msg, COLORS["error"])
            return

        success, err = self._data_manager.add(target)
        if success:
            self._add_card(target)
            self._entry.delete(0, "end")
            self._status_bar.set_status(f"已添加: {target}", COLORS["success"])
            self._update_count()
        else:
            self._status_bar.set_status(err, COLORS["error"])

    def _add_card(self, target):
        if target in self._cards:
            return
        
        def on_delete(t):
            self._delete_target(t)

        card = TargetCard(self._scroll_frame, target=target, on_delete=on_delete)
        card.grid(row=self._next_row, column=0, sticky="ew", pady=2)
        self._next_row += 1
        self._cards[target] = card

    def _delete_target(self, target):
        if target in self._workers:
            # 仅发停止信号，不阻塞等待线程（线程为 daemon，卡片销毁后结果自然被丢弃）
            self._workers[target].request_stop()
            del self._workers[target]
        
        success, err = self._data_manager.delete(target)
        if success:
            if target in self._cards:
                self._cards[target].destroy()
                del self._cards[target]
            self._status_bar.set_status(f"已删除: {target}", COLORS["warning"])
            self._update_count()
        else:
            self._status_bar.set_status(err, COLORS["error"])

    def _start_all(self):
        if self._is_pinging:
            return
        if not self._cards:
            self._status_bar.set_status("请先添加目标", COLORS["warning"])
            return
        self._is_pinging = True
        # 丢弃上一轮残留的过期结果，避免开局瞬间刷新旧数据
        self._drain_result_queue()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._entry.configure(state="disabled")
        self._add_btn.configure(state="disabled")
        
        for target, card in self._cards.items():
            if target not in self._workers:
                worker = PingWorker(
                    target,
                    callback=lambda r, t=target: self._result_queue.put((t, r)),
                )
                self._workers[target] = worker
                worker.start()
        
        self._status_bar.set_status("正在 Ping...", COLORS["info"])
        self._update_count()

    def _stop_all(self):
        if not self._is_pinging:
            return
        self._is_pinging = False

        # 先批量发送停止信号并终止子进程，再统一 join，
        # 避免逐个 worker.stop() 时每个都同步等待 0.2s 造成 UI 卡顿。
        workers = list(self._workers.values())
        for worker in workers:
            worker.request_stop()
        deadline = time.monotonic() + 0.3
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                worker.stop()
        self._workers.clear()
        self._drain_result_queue()

        for card in self._cards.values():
            card.reset()

        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._entry.configure(state="normal")
        self._add_btn.configure(state="normal")
        self._status_bar.set_status("已停止", COLORS["text_dim"])
        self._update_count()

    def _schedule_ui_poll(self):
        """持续调度主线程轮询（窗口关闭后停止自续）。

        所有跨线程结果——Ping 结果与 Tailscale/防火墙的控制结果——都经队列回主线程
        处理，后台线程不直接触碰 Tk 控件。100ms 一次空轮询开销可忽略。
        """
        if self._closing:
            return
        try:
            self.after(self._POLL_INTERVAL_MS, self._poll_queues)
        except Exception as e:
            logger.debug(f"轮询调度结束: {e}")

    def _poll_queues(self):
        """主线程批量消费两个队列：Ping 结果刷新卡片，控制结果刷新状态。"""
        if self._closing:
            return
        try:
            if not self.winfo_exists():
                return
            self._apply_ping_results()
            self._apply_control_messages()
        except Exception as e:
            # 窗口销毁瞬间 after 回调可能抛 TclError，记录后停止轮询即可
            logger.debug(f"轮询刷新异常: {e}")
            return
        self._schedule_ui_poll()

    def _apply_ping_results(self):
        """消费 Ping 结果队列并刷新对应卡片（队列为空时开销极小）。"""
        while True:
            try:
                target, result = self._result_queue.get_nowait()
            except queue.Empty:
                return
            card = self._cards.get(target)
            if card is not None:
                card.update_status(result)

    def _apply_control_messages(self):
        """消费后台控制结果（Tailscale / 防火墙）并刷新对应卡片。"""
        while True:
            try:
                kind, payload = self._control_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "tailscale":
                self._tailscale_card.update_status(payload["success"], payload["message"])
                self._status_bar.set_status(
                    "Tailscale 重启成功" if payload["success"] else "Tailscale 重启失败",
                    COLORS["success"] if payload["success"] else COLORS["error"],
                )
            elif kind == "firewall":
                self._firewall_card.set_busy(False)
                self._firewall_card.update_state(payload["state"], payload.get("detail", ""))
                if payload["message"]:
                    self._status_bar.set_status(
                        payload["message"],
                        COLORS["success"] if payload["success"] else COLORS["error"],
                    )

    def _drain_result_queue(self):
        """清空未消费的结果（停止后丢弃过期结果，防止残留刷新）。"""
        q = self._result_queue
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break

    def _update_count(self):
        total = len(self._cards)
        pinging = len(self._workers)
        self._status_bar.set_count(total, pinging)

    def _restart_tailscale(self):
        if not messagebox.askokcancel("确认", "确定要重启 Tailscale 服务吗？"):
            # 取消时不做任何状态变更：按钮状态在确认之后才置为「重启中」
            return
        self._tailscale_card.set_busy(True)

        def do_restart():
            try:
                success, message = self._tailscale.restart()
            except Exception as e:
                logger.error(f"重启 Tailscale 异常: {e}")
                success, message = False, f"重启异常: {e}"
            # 经队列回主线程刷新 UI，避免后台线程直接调用 Tk 的 after/configure
            self._control_queue.put(
                ("tailscale", {"success": success, "message": message})
            )
        threading.Thread(target=do_restart, daemon=True).start()

    # ---- Windows 防火墙 ----

    # 提权请求由用户确认后异步执行，等待其完成再复查状态
    _FIREWALL_ELEVATION_WAIT = 6.0

    def _refresh_firewall_state(self):
        """启动时读取一次防火墙状态（读注册表，无需提权）。"""
        self._firewall_action("refresh")

    def _firewall_action(self, action):
        """处理防火墙卡片动作：off 关闭 / on 开启 / refresh 只刷新状态。"""
        if action == "off":
            confirmed = messagebox.askokcancel(
                "确认关闭防火墙",
                "关闭 Windows 防火墙会降低系统的安全防护，\n"
                "同一网络中的其他设备可能更容易访问本机。\n\n"
                "确定要关闭吗？",
            )
            if not confirmed:
                return

        self._firewall_card.set_busy(True, action)

        def do_action():
            try:
                if action == "off":
                    success, message, elevated = self._firewall.disable()
                elif action == "on":
                    success, message, elevated = self._firewall.enable()
                else:
                    success, message, elevated = True, "", False
            except Exception as e:
                logger.error(f"防火墙操作异常: {e}")
                success, message, elevated = False, f"防火墙操作异常: {e}", False

            if success and elevated:
                # 命令由 UAC 窗口异步执行，稍候再读一次真实状态
                time.sleep(self._FIREWALL_ELEVATION_WAIT)
            state = self._firewall.query_state()

            if not success:
                detail = message
            elif elevated:
                detail = "已发起管理员请求，确认后会自动复查状态，也可点「刷新」"
            else:
                detail = ""
            self._control_queue.put((
                "firewall",
                {
                    "success": success,
                    "message": message,
                    "state": state,
                    "detail": detail,
                },
            ))

        threading.Thread(target=do_action, daemon=True).start()

    def _cleanup_on_exit(self):
        """atexit 兜底清理：批量停止所有 worker（异常退出时也生效）。

        与 _stop_all 相同的批量模式：先统一发停止信号，再按总 deadline 有界 join，
        避免逐个 stop() 同步等待导致退出卡顿。
        """
        self._closing = True
        self._is_pinging = False
        workers = list(self._workers.values())
        for worker in workers:
            try:
                worker.request_stop()
            except Exception:
                pass
        deadline = time.monotonic() + 0.3
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    worker.stop()
                except Exception:
                    pass
        self._workers.clear()

    def _on_close(self):
        logger.info("正在关闭应用...")
        self._closing = True
        self._cleanup_on_exit()
        try:
            self.destroy()
        except Exception:
            pass
