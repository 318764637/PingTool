"""
Ping-Tailscale Windows 桌面工具
===============================
一键 Ping + Tailscale 管理的 Win11 风格桌面程序。
"""

import subprocess
import re
import threading
import time
import json
import os
import sys
import ctypes
from collections import deque


# ============================================================
# 数据层：DataManager
# ============================================================

class DataManager:
    """管理 targets.json 的读写，提供增删查接口。"""

    @staticmethod
    def _data_path() -> str:
        """获取数据文件路径（与 exe/main.py 同目录）。"""
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "targets.json")

    @classmethod
    def load(cls) -> list:
        """读取目标列表，文件不存在则返回空列表。"""
        path = cls._data_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, PermissionError):
            return []

    @classmethod
    def save(cls, targets: list) -> bool:
        """保存目标列表到文件。"""
        path = cls._data_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(targets, f, ensure_ascii=False, indent=2)
            return True
        except (PermissionError, OSError):
            return False

    @classmethod
    def add(cls, target: str) -> bool:
        """添加一个目标（去重），返回 True 表示新增成功。"""
        target = target.strip()
        if not target:
            return False
        targets = cls.load()
        if target in targets:
            return False  # 已存在
        targets.append(target)
        return cls.save(targets)

    @classmethod
    def delete(cls, target: str) -> bool:
        """删除一个目标，返回 True 表示删除成功。"""
        targets = cls.load()
        if target not in targets:
            return False
        targets.remove(target)
        return cls.save(targets)


# ============================================================
# 业务层：PingWorker
# ============================================================

class PingWorker:
    """在独立线程中循环执行 Ping，通过回调返回结果。"""

    def __init__(self, callback):
        """
        Args:
            callback: 每次 ping 完成后调用，接收 dict
                      {"target": str, "seq": int, "latency": float|None, "timeout": bool}
        """
        self._callback = callback
        self._thread = None
        self._running = False
        self._target = ""
        self._proc = None
        self._lock = threading.Lock()

    def start(self, target: str):
        """启动 Ping 线程。"""
        if self._running:
            return
        self._target = target.strip()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止 worker：发信号 + 终止正在跑的 ping 子进程 + 短暂 join（最多 0.2s）。"""
        self._request_stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)

    def _request_stop(self):
        """仅发停止信号并杀掉当前 ping 子进程，不等待线程。"""
        self._running = False
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def is_running(self) -> bool:
        return self._running

    def _run(self):
        """线程主循环：每秒 ping 一次目标。"""
        seq = 0
        while self._running:
            seq += 1
            result = self._ping_once(self._target, seq)
            if not self._running:
                return
            result["target"] = self._target
            if self._callback:
                try:
                    self._callback(result)
                except Exception:
                    pass
            for _ in range(10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _ping_once(self, target: str, seq: int) -> dict:
        """执行一次 ping，返回结构化结果。"""
        try:
            proc = subprocess.Popen(
                ["ping", "-n", "1", "-w", "3000", target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (FileNotFoundError, OSError):
            return {"seq": seq, "latency": None, "timeout": True}

        self._proc = proc
        try:
            try:
                stdout, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.communicate(timeout=1)
                except Exception:
                    pass
                return {"seq": seq, "latency": None, "timeout": True}

            try:
                output = stdout.decode("gbk")
            except UnicodeDecodeError:
                output = stdout.decode("gbk", errors="replace")

            if re.search(r"(?:时间|time)<1ms", output, re.IGNORECASE):
                return {"seq": seq, "latency": 0.5, "timeout": False}

            time_match = re.search(r"(?:时间|time)[=<](\d+)ms", output, re.IGNORECASE)
            if time_match:
                return {"seq": seq, "latency": float(time_match.group(1)), "timeout": False}

            return {"seq": seq, "latency": None, "timeout": True}
        finally:
            self._proc = None


# ============================================================
# 业务层：TailscaleManager
# ============================================================

class TailscaleManager:
    """管理 Tailscale Windows 服务的重启。"""

    SERVICE_NAME = "Tailscale"

    @classmethod
    def restart(cls) -> dict:
        """重启 Tailscale 服务，返回 {"success": bool, "message": str}。"""
        if not cls._is_admin():
            # 以管理员权限重新执行 sc 命令
            return cls._restart_with_uac()

        try:
            # 停止服务
            stop_result = subprocess.run(
                ["sc", "stop", cls.SERVICE_NAME],
                capture_output=True, text=True, encoding="gbk", timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # 等待服务完全停止
            time.sleep(3)

            # 启动服务
            start_result = subprocess.run(
                ["sc", "start", cls.SERVICE_NAME],
                capture_output=True, text=True, encoding="gbk", timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if "RUNNING" in start_result.stdout or "成功" in start_result.stdout:
                return {"success": True, "message": "Tailscale 重启成功"}
            elif start_result.returncode != 0:
                return {"success": False, "message": f"启动失败: {start_result.stderr.strip()}"}
            else:
                return {"success": True, "message": "Tailscale 已重启"}

        except subprocess.TimeoutExpired:
            return {"success": False, "message": "操作超时，请检查 Tailscale 服务状态"}
        except FileNotFoundError:
            return {"success": False, "message": "未找到 sc 命令，系统异常"}
        except OSError as e:
            return {"success": False, "message": f"系统错误: {e}"}

    @classmethod
    def _is_admin(cls) -> bool:
        """检查当前是否有管理员权限。"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    @classmethod
    def _restart_with_uac(cls) -> dict:
        """以管理员权限提权重启 Tailscale。"""
        # 构建一个批处理：先停后启
        batch = f'@echo off\nsc stop {cls.SERVICE_NAME}\ntimeout /t 3 /nobreak >nul\nsc start {cls.SERVICE_NAME}\npause\n'
        batch_path = os.path.join(os.environ.get("TEMP", os.getcwd()), "tailscale_restart.bat")
        try:
            with open(batch_path, "w", encoding="gbk") as f:
                f.write(batch)
            # 以 runas 方式运行批处理
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", batch_path, None, None, 1  # SW_SHOWNORMAL
            )
            return {"success": True, "message": "已弹出管理员确认窗口，请在弹出的窗口中确认并等待完成"}
        except OSError as e:
            return {"success": False, "message": f"无法提权: {e}"}


# ============================================================
# UI 层：PingApp（customtkinter 主窗口）— 多目标版
# ============================================================

import customtkinter as ctk
from tkinter import messagebox

# ── 配色常量 ────────────────────────────────────────────────
CLR_BG_START     = "#E8F4FD"
CLR_BG_END       = "#C8E4F8"
CLR_SURFACE      = "#FFFFFF"
CLR_PRIMARY      = "#3B82F6"
CLR_PRIMARY_HOV  = "#2563EB"
CLR_DANGER       = "#EF4444"
CLR_DANGER_HOV   = "#DC2626"
CLR_SUCCESS      = "#10B981"
CLR_WARNING      = "#F59E0B"
CLR_TEXT         = "#1E293B"
CLR_TEXT_SEC     = "#64748B"
CLR_BORDER       = "#CBD5E1"

# ── 字体配置 ─────────────────────────────────────────────────
FONT_FAMILY = "Segoe UI Variable"
FONT_TITLE  = (FONT_FAMILY, 18, "bold")
FONT_HEADER = (FONT_FAMILY, 15)
FONT_BODY   = (FONT_FAMILY, 14)
FONT_SMALL  = (FONT_FAMILY, 12)
FONT_MONO   = (FONT_FAMILY, 13, "bold")

# ── 延迟颜色映射 ─────────────────────────────────────────────
def latency_color(ms: float | None) -> str:
    if ms is None:      return CLR_TEXT_SEC
    if ms < 30:         return CLR_SUCCESS
    if ms < 80:         return CLR_PRIMARY
    if ms < 150:        return CLR_WARNING
    return CLR_DANGER

def latency_dot(ms: float | None) -> str:
    """延迟 → 小圆点指示器。"""
    if ms is None:      return "⚫"
    if ms < 30:         return "🟢"
    if ms < 80:         return "🔵"
    if ms < 150:        return "🟡"
    return "🔴"


class PingApp(ctk.CTk):
    """主窗口 — 多目标同时 Ping。"""

    def __init__(self):
        super().__init__()

        # ── 窗口基础设置 ──
        self.title("Ping Tool")
        self.geometry("500x550")
        self.minsize(440, 500)
        self.resizable(True, True)

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 500) // 2
        y = (sh - 550) // 2
        self.geometry(f"500x550+{x}+{y}")

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ── 状态变量 ──
        self._targets = DataManager.load()          # 目标名字列表
        self._workers: dict[str, PingWorker] = {}   # 每个目标一个 worker
        self._buffers: dict[str, deque] = {}         # 每个目标一个环形缓冲区
        self._ping_rows: dict[str, dict] = {}        # 每个目标的 UI 组件引用
        self._is_pinging = False

        # ── 构建 UI ──
        self._build_ui()

    # ════════════════════════════════════════════════════════
    # UI 构建
    # ════════════════════════════════════════════════════════

    def _build_ui(self):
        self.configure(fg_color=CLR_BG_START)

        # 主滚动容器
        self._outer = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._outer.pack(fill="both", expand=True, padx=16, pady=(12, 4))

        # 标题
        title_frame = ctk.CTkFrame(self._outer, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(title_frame, text="🔵 Ping & Tailscale 工具",
                     font=FONT_TITLE, text_color=CLR_TEXT).pack(side="left")

        # ── 目标管理卡片 ──
        self._build_target_card()

        # ── Tailscale 卡片 ──
        self._build_tailscale_card()

        # ── 状态栏 ──
        self._build_statusbar()

        # 初始化目标列表
        self._rebuild_target_rows()

    def _build_target_card(self):
        """目标管理卡片：输入区 + 目标列表 + 启停按钮。"""
        card = ctk.CTkFrame(self._outer, fg_color=CLR_SURFACE,
                            corner_radius=10, border_width=1, border_color=CLR_BORDER)
        card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(card, text="📋 我的目标", font=FONT_HEADER,
                     text_color=CLR_TEXT).pack(anchor="w", padx=14, pady=(10, 6))

        # 添加行
        add_row = ctk.CTkFrame(card, fg_color="transparent")
        add_row.pack(fill="x", padx=14, pady=(0, 8))

        self._target_entry = ctk.CTkEntry(
            add_row, placeholder_text="输入 IP 或域名，例如 8.8.8.8",
            height=32, corner_radius=6, font=FONT_BODY,
        )
        self._target_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._target_entry.bind("<Return>", lambda e: self._add_target())

        self._add_btn = ctk.CTkButton(
            add_row, text="➕ 添加", width=70, height=32,
            corner_radius=6, fg_color=CLR_PRIMARY, hover_color=CLR_PRIMARY_HOV,
            font=FONT_SMALL, command=self._add_target,
        )
        self._add_btn.pack(side="left")

        # 分隔线
        sep = ctk.CTkFrame(card, fg_color=CLR_BORDER, height=1)
        sep.pack(fill="x", padx=14)

        # 目标列表容器（每个目标一行）
        self._rows_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._rows_frame.pack(fill="x", padx=4, pady=(4, 0))

        # 空状态提示
        self._empty_label = ctk.CTkLabel(
            self._rows_frame,
            text="还没有目标，在上方输入后点击「添加」",
            font=FONT_SMALL, text_color=CLR_TEXT_SEC,
        )

        # 分隔线
        sep2 = ctk.CTkFrame(card, fg_color=CLR_BORDER, height=1)
        sep2.pack(fill="x", padx=14, pady=(6, 0))

        # 启停按钮行
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(8, 10))

        self._start_btn = ctk.CTkButton(
            btn_row, text="▶ 开始 Ping 全部", width=150, height=36,
            corner_radius=8, fg_color=CLR_PRIMARY, hover_color=CLR_PRIMARY_HOV,
            font=FONT_BODY, command=self._start_all,
        )
        self._start_btn.pack(side="left", padx=(0, 10))

        self._stop_btn = ctk.CTkButton(
            btn_row, text="⏹ 停止全部", width=120, height=36,
            corner_radius=8, fg_color="transparent", hover_color="#FEE2E2",
            text_color=CLR_DANGER, border_width=1, border_color=CLR_DANGER,
            font=FONT_BODY, command=self._stop_all, state="disabled",
        )
        self._stop_btn.pack(side="left")

    def _build_target_row(self, target: str) -> dict:
        """为单个目标创建一行 UI，返回组件引用字典。"""
        row = ctk.CTkFrame(self._rows_frame, fg_color=CLR_BG_START,
                           corner_radius=8)
        row.pack(fill="x", pady=(0, 3))

        # 左侧：目标名
        name_label = ctk.CTkLabel(row, text=target, font=FONT_MONO,
                                  text_color=CLR_TEXT, width=130, anchor="w")
        name_label.pack(side="left", padx=(10, 2))

        # 中间：4 个延迟小方块
        blocks = []
        for i in range(4):
            blk = ctk.CTkFrame(row, fg_color=CLR_BORDER,
                               corner_radius=3, width=14, height=14)
            blk.pack(side="left", padx=(2, 2), pady=8)
            blk.pack_propagate(False)
            # 方块的"填充"子组件
            inner = ctk.CTkFrame(blk, fg_color=CLR_BORDER, corner_radius=2)
            inner.place(relwidth=0.85, relheight=0.85, relx=0.5, rely=0.5, anchor="center")
            blocks.append((blk, inner))

        # 平均延迟
        avg_label = ctk.CTkLabel(row, text="-- ms", font=FONT_SMALL,
                                 text_color=CLR_TEXT_SEC, width=50)
        avg_label.pack(side="left", padx=(6, 2))

        # 状态指示灯
        dot_label = ctk.CTkLabel(row, text="⚫", font=(FONT_FAMILY, 10))
        dot_label.pack(side="left", padx=(2, 6))

        # 右侧：删除按钮
        del_btn = ctk.CTkButton(
            row, text="❌", width=28, height=28,
            corner_radius=6, fg_color="transparent",
            hover_color="#FEE2E2", text_color=CLR_DANGER,
            font=FONT_SMALL,
            command=lambda t=target: self._remove_target(t),
        )
        del_btn.pack(side="right", padx=(0, 4))

        return {
            "row": row, "name": name_label,
            "blocks": blocks, "avg": avg_label,
            "dot": dot_label, "del": del_btn,
        }

    def _rebuild_target_rows(self):
        """全量重建目标列表 UI。"""
        # 清除旧行
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._ping_rows.clear()

        if not self._targets:
            self._empty_label = ctk.CTkLabel(
                self._rows_frame,
                text="还没有目标，在上方输入后点击「添加」",
                font=FONT_SMALL, text_color=CLR_TEXT_SEC,
            )
            self._empty_label.pack(pady=(8, 8))

            # 如果没有目标，禁用开始按钮
            if not self._is_pinging:
                self._start_btn.configure(state="disabled")
        else:
            self._start_btn.configure(state="normal" if not self._is_pinging else "disabled")
            for t in self._targets:
                self._ping_rows[t] = self._build_target_row(t)
                # 初始化缓冲区
                if t not in self._buffers:
                    self._buffers[t] = deque(maxlen=4)

    def _build_tailscale_card(self):
        """Tailscale 管理区。"""
        card = ctk.CTkFrame(self._outer, fg_color=CLR_SURFACE,
                            corner_radius=10, border_width=1, border_color=CLR_BORDER)
        card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(card, text="🔄 Tailscale 管理", font=FONT_HEADER,
                     text_color=CLR_TEXT).pack(anchor="w", padx=14, pady=(10, 4))

        ta_row = ctk.CTkFrame(card, fg_color="transparent")
        ta_row.pack(fill="x", padx=14, pady=(0, 10))

        self._restart_ts_btn = ctk.CTkButton(
            ta_row, text="🔄 重启 Tailscale", width=140, height=36,
            corner_radius=8, fg_color=CLR_PRIMARY, hover_color=CLR_PRIMARY_HOV,
            font=FONT_BODY, command=self._restart_tailscale,
        )
        self._restart_ts_btn.pack(side="left")

        self._ts_status_label = ctk.CTkLabel(
            ta_row, text="", font=FONT_SMALL, text_color=CLR_TEXT_SEC,
        )
        self._ts_status_label.pack(side="left", padx=(12, 0))

    def _build_statusbar(self):
        """底部状态栏。"""
        bar = ctk.CTkFrame(self, fg_color="transparent", height=24)
        bar.pack(fill="x", padx=16, pady=(0, 4))
        bar.pack_propagate(False)

        self._status_bar = ctk.CTkLabel(
            bar, text="就绪", font=FONT_SMALL, text_color=CLR_TEXT_SEC,
        )
        self._status_bar.pack(side="left")
        ctk.CTkLabel(bar, text="v1.1", font=FONT_SMALL,
                     text_color=CLR_TEXT_SEC).pack(side="right")

    # ════════════════════════════════════════════════════════
    # 交互逻辑
    # ════════════════════════════════════════════════════════

    def _add_target(self):
        """添加新目标到列表。"""
        target = self._target_entry.get().strip()
        if not target:
            self._set_status("请输入有效的 IP 地址或域名")
            return
        if DataManager.add(target):
            self._targets = DataManager.load()
            self._target_entry.delete(0, "end")
            self._rebuild_target_rows()
            self._set_status(f"已添加: {target}")
        else:
            if target in self._targets:
                self._set_status(f"'{target}' 已在列表中")
            else:
                self._set_status("保存失败，请检查文件权限")

    def _remove_target(self, target: str):
        """从列表中删除目标。"""
        # 如果正在 ping 该目标，先停止
        self._stop_one(target)

        if DataManager.delete(target):
            self._targets = DataManager.load()
            self._buffers.pop(target, None)
            self._rebuild_target_rows()
            self._set_status(f"已删除: {target}")
        else:
            self._set_status("删除失败")

    def _start_all(self):
        """为所有目标启动 Ping。"""
        if not self._targets:
            self._set_status("请先添加目标")
            return

        self._is_pinging = True
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._add_btn.configure(state="disabled")
        self._target_entry.configure(state="disabled")

        count = 0
        for t in self._targets:
            if t not in self._workers or not self._workers[t].is_running():
                w = PingWorker(self._on_ping_result)
                self._workers[t] = w
                if t not in self._buffers:
                    self._buffers[t] = deque(maxlen=4)
                w.start(t)
                count += 1
            # 更新行指示灯
            if t in self._ping_rows:
                self._ping_rows[t]["dot"].configure(text="🟡")

        self._set_status(f"已启动 {count} 个目标 Ping")

    def _stop_all(self):
        """停止所有 Ping：先批量发信号 + 杀子进程，再短暂 join（daemon 兜底）。"""
        self._is_pinging = False

        threads = []
        for w in self._workers.values():
            w._request_stop()
            if w._thread:
                threads.append(w._thread)
        self._workers.clear()

        deadline = time.time() + 0.3
        for th in threads:
            remaining = max(0.0, deadline - time.time())
            if remaining > 0 and th.is_alive():
                th.join(timeout=remaining)

        self._start_btn.configure(state="normal" if self._targets else "disabled")
        self._stop_btn.configure(state="disabled")
        self._add_btn.configure(state="normal")
        self._target_entry.configure(state="normal")

        for t, row in self._ping_rows.items():
            row["dot"].configure(text="⚫")
        self._set_status("已停止")

    def _stop_one(self, target: str):
        """停止单个目标的 Ping。"""
        if target in self._workers:
            self._workers[target].stop()
            del self._workers[target]
        if target in self._ping_rows:
            self._ping_rows[target]["dot"].configure(text="⚫")
            # 清空该行的显示
            row = self._ping_rows[target]
            for blk, inner in row["blocks"]:
                inner.configure(fg_color=CLR_BORDER)
            row["avg"].configure(text="-- ms")

    # ── Ping 回调 ─────────────────────────────────────────

    def _on_ping_result(self, result: dict):
        """PingWorker 回调（worker 线程中）→ 投递到主线程。"""
        self.after(0, self._update_row, result)

    def _update_row(self, r: dict):
        """在主线程更新某个目标的行显示。"""
        target = r["target"]
        if target not in self._buffers:
            return
        self._buffers[target].append(r)
        buf = list(self._buffers[target])
        row = self._ping_rows.get(target)
        if not row:
            return

        # 更新 4 个色块
        for i, (blk, inner) in enumerate(row["blocks"]):
            if i < len(buf):
                entry = buf[i]
                if entry["timeout"]:
                    inner.configure(fg_color=CLR_TEXT_SEC)
                else:
                    inner.configure(fg_color=latency_color(entry["latency"]))
            else:
                inner.configure(fg_color=CLR_BORDER)

        # 更新平均延迟
        valid = [x["latency"] for x in buf if not x["timeout"]]
        if valid:
            avg = sum(valid) / len(valid)
            row["avg"].configure(text=f"{avg:.0f} ms", text_color=CLR_TEXT)
        else:
            if buf and all(x["timeout"] for x in buf):
                row["avg"].configure(text="超时", text_color=CLR_DANGER)
            else:
                row["avg"].configure(text="-- ms", text_color=CLR_TEXT_SEC)

        # 更新状态灯：取最近一次
        latest = buf[-1]
        row["dot"].configure(text=latency_dot(
            None if latest["timeout"] else latest["latency"]
        ))

    # ── Tailscale ──────────────────────────────────────────

    def _restart_tailscale(self):
        """重启 Tailscale 服务。"""
        ok = messagebox.askokcancel(
            "确认重启 Tailscale",
            "将要重启 Tailscale 服务，\n\n"
            "你的 Tailscale 连接会短暂中断（约 3-5 秒），\n"
            "确定要继续吗？",
        )
        if not ok:
            return

        self._restart_ts_btn.configure(text="重启中...", state="disabled")
        self._ts_status_label.configure(text="正在重启...", text_color=CLR_TEXT_SEC)
        self.update_idletasks()

        def _do_restart():
            result = TailscaleManager.restart()
            self.after(0, self._on_restart_done, result)

        threading.Thread(target=_do_restart, daemon=True).start()

    def _on_restart_done(self, result: dict):
        self._restart_ts_btn.configure(text="🔄 重启 Tailscale", state="normal")
        if result["success"]:
            self._ts_status_label.configure(
                text=f"✅ {result['message']}", text_color=CLR_SUCCESS)
        else:
            self._ts_status_label.configure(
                text=f"❌ {result['message']}", text_color=CLR_DANGER)

    # ── 辅助 ────────────────────────────────────────────────

    def _set_status(self, text: str):
        self._status_bar.configure(text=text)

    def _on_close(self):
        """窗口关闭：停止所有 worker。"""
        self._stop_all()
        self.destroy()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    app = PingApp()
    app.mainloop()
