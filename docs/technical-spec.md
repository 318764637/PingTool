# 技术规格说明

> 项目：Ping-Tailscale Windows 桌面工具
> 版本：v1.0
> 创建日期：2026-06-07

---

## 一、技术栈

| 层面 | 技术选择 | 版本要求 | 说明 |
|------|----------|----------|------|
| 语言 | Python | ≥ 3.9 | 稳定版本即可 |
| UI 框架 | customtkinter | ≥ 5.2 | 基于 tkinter 的现代 UI 封装 |
| GUI 基础 | tkinter | Python 内置 | customtkinter 的底层依赖 |
| Ping 实现 | subprocess (ping.exe) | Windows 内置 | 调用系统原生 ping 命令 |
| 数据存储 | JSON | Python 内置 | 轻量级持久化 |
| 多线程 | threading | Python 内置 | 避免 Ping 阻塞 UI |
| 打包 | PyInstaller | ≥ 6.0 | 生成单个 exe |

## 二、架构设计

### 单文件架构

```
main.py
├── DataManager         # 数据层：读写 targets.json
├── PingWorker          # 业务层：Ping 线程管理
├── TailscaleManager    # 业务层：Tailscale 服务控制
├── PingApp (CTk)       # UI 层：继承 customtkinter.CTk
│   ├── build_ui()      #   构建界面
│   ├── update_display()#   刷新延迟数据
│   └── on_close()      #   窗口关闭清理
└── main()              # 入口函数
```

### 类职责

| 类名 | 职责 | 依赖 |
|------|------|------|
| `DataManager` | 管理 targets.json 的读写，提供 add/delete/get_all 接口 | json, os |
| `PingWorker` | 在独立线程中循环执行 ping，结果通过回调通知 UI | subprocess, threading, re |
| `TailscaleManager` | 执行 sc stop/start 命令，返回执行结果 | subprocess, ctypes |
| `PingApp` | 主窗口，组合所有 UI 组件，协调各模块 | customtkinter |

### 数据流

```
用户点击"开始 Ping"
  → PingApp.start_ping()
    → PingWorker.start(target, callback)
      → 新线程: while running: ping(target) → callback(result)
        → PingApp.on_ping_result(result)
          → 更新环形缓冲区 → 更新 UI 卡片 → 更新平均值

用户点击"添加目标"
  → PingApp.add_target()
    → DataManager.add(target)
      → 写入 targets.json
    → 刷新下拉框

用户点击"重启 Tailscale"
  → PingApp.restart_tailscale()
    → 确认对话框
      → TailscaleManager.restart()
        → sc stop Tailscale → 等待3秒 → sc start Tailscale
        → 返回结果 → 状态栏显示
```

## 三、关键接口

### DataManager

```python
class DataManager:
    DATA_FILE = "targets.json"

    @classmethod
    def load() -> list[str]          # 读取文件返回目标列表
    @classmethod
    def save(targets: list[str])     # 保存列表到文件
    @classmethod
    def add(target: str) -> bool     # 添加目标，返回是否成功
    @classmethod
    def delete(target: str) -> bool  # 删除目标，返回是否成功
```

### PingWorker

```python
class PingWorker:
    def __init__(self, callback: Callable[[dict], None])
    def start(self, target: str)
    def stop(self)
    def is_running() -> bool
    # callback 收到: {"seq": int, "latency": float|None, "timeout": bool}
```

### TailscaleManager

```python
class TailscaleManager:
    SERVICE_NAME = "Tailscale"

    @classmethod
    def restart() -> dict   # 返回 {"success": bool, "message": str}
    @classmethod
    def is_admin() -> bool  # 检查是否有管理员权限
```

## 四、数据格式

### targets.json

```json
[
    "8.8.8.8",
    "1.1.1.1",
    "baidu.com",
    "192.168.1.1"
]
```

- UTF-8 编码
- 最多保存 20 条（UI 层面建议 5-10 条）
- 去重：同名目标不重复添加
- 空列表时显示提示文字

### Ping 结果（内部）

```python
{
    "seq": 1,           # 序列号
    "latency": 12.5,    # ms，超时时为 None
    "timeout": False,   # 是否超时
    "timestamp": 1.7e9  # time.time()
}
```

## 五、线程安全

- Ping 子线程只负责执行和通过 `after()` 投递结果
- 所有 UI 更新在主线程（tkinter 事件循环）中执行
- `running` 标志位设为原子布尔值，控制启停
- 窗口关闭时确保线程结束（`daemon=True` + `join(2)`）
