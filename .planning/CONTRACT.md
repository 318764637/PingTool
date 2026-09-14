# Ping Tool 模块接口规范（CONTRACT）

> 生成日期：2026-06-07
> 本文件描述 `ping_tool/`（Python）各模块间的接口契约，以及 Python / C++ 两版共享的数据契约。
> 所有接口均为**现状实际代码**中已存在、本次修复后**保持或增强**的签名。

---

## 一、配置层 `ping_tool/config.py`

### 1.1 公开符号

```python
APP_NAME: str                       # "PingTool"
APP_VERSION: str                    # "1.1.0"
DEFAULT_CONFIG: dict                # 默认配置（键见下表）

def get_config() -> Config          # 返回模块级单例

class Config:
    def get(self, key: str, default=None) -> Any   # 读取配置项
    def __getitem__(self, key: str) -> Any          # 等价 get，无默认
    def save(self) -> None                          # 写回 %APPDATA%/PingTool/config.json
```

### 1.2 配置项契约（键 → 类型 → 默认值 → 环境变量）

| key | 类型 | 默认 | 环境变量 `PINGTOOL_<KEY>` |
|-----|------|------|---------------------------|
| `window_width` | int | 500 | `PINGTOOL_WINDOW_WIDTH` |
| `window_height` | int | 640 | `PINGTOOL_WINDOW_HEIGHT` |
| `ping_interval` | float | 1.0（秒） | `PINGTOOL_PING_INTERVAL` |
| `ping_timeout` | int | 3000（毫秒） | `PINGTOOL_PING_TIMEOUT` |
| `buffer_size` | int | 4 | `PINGTOOL_BUFFER_SIZE` |
| `max_targets` | int | 20 | `PINGTOOL_MAX_TARGETS` |
| `log_max_bytes` | int | 5*1024*1024 | `PINGTOOL_LOG_MAX_BYTES` |
| `log_backup_count` | int | 3 | `PINGTOOL_LOG_BACKUP_COUNT` |
| `tailscale_stop_wait` | int | 3 | `PINGTOOL_TAILSCALE_STOP_WAIT` |
| `tailscale_cmd_timeout` | int | 30 | `PINGTOOL_TAILSCALE_CMD_TIMEOUT` |
| `firewall_cmd_timeout` | int | 30 | `PINGTOOL_FIREWALL_CMD_TIMEOUT` |

### 1.3 环境变量类型转换规则（修复后）

1. 目标类型为 `bool`：`1/true/yes/on`（大小写不敏感）→ `True`，其余 → `False`。
2. 目标类型为 `int/float`：`type(default)(env_val)`，失败则忽略该变量（保留默认）。
3. 目标类型为 `str`：直接使用。
4. 解析失败**不得抛异常**（记录后忽略）。

---

## 二、日志层 `ping_tool/logger.py`

```python
def setup_logger(name: str | None = None, log_file: Path | None = None) -> logging.Logger
    # 幂等：已有 handlers 时直接返回。默认日志文件 %LOCALAPPDATA%/PingTool/logs/pingtool.log
    # 文件级 DEBUG、控制台级 INFO，RotatingFileHandler 轮转（log_max_bytes / log_backup_count）

def get_logger(name: str | None = None) -> logging.Logger
    # 惰性获取，不重复配置 handler。模块级用法：logger = get_logger(__name__)
```

**约定**：模块内一律 `from ..logger import get_logger` 后取 `logger = get_logger(__name__)`；禁止在业务路径中打印裸 `print`。

---

## 三、数据层 `ping_tool/data/manager.py`

### 3.1 类与签名

```python
class DataManager:
    def __init__(self, file_path: Path | str | None = None)
        # 默认路径：打包(frozen) → exe 同目录/targets.json；源码 → 项目根/targets.json

    def load(self) -> list[str]              # 返回字符串列表；文件缺失/损坏 → []；去重
    def save(self, targets: list[str]) -> bool
        # 原子写：临时文件 + os.replace；失败记录日志返回 False
    def add(self, target: str) -> tuple[bool, str]
        # 内部先 sanitize（strip + 域名小写）；空/超长/非法 → (False, 原因)
        # 去重；达到 max_targets → (False, "最多添加 N 个目标")
    def delete(self, target: str) -> tuple[bool, str]
```

### 3.2 数据文件契约（Python/C++ 共享）

```
文件：targets.json（UTF-8，无 BOM，缩进 2）
格式：["8.8.8.8", "baidu.com"]        —— 顶层必须为字符串数组
兼容：单元素、空数组、含多余空白均须可读；损坏文件按空列表处理，不崩溃
```

---

## 四、业务层 `ping_tool/core/ping_worker.py`

### 4.1 类与签名

```python
class PingWorker:
    def __init__(self, target: str, callback: Callable[[dict], None],
                 interval: float | None = None, timeout_ms: int | None = None)
        # interval 默认取 config.ping_interval；timeout_ms 默认取 config.ping_timeout
        # 构造即创建 daemon 线程骨架，start() 才真正运行

    @property
    def is_running(self) -> bool

    def start(self) -> None     # 幂等：已运行则直接返回
    def stop(self) -> None      # 置停止标志 + 终止当前子进程 + join(timeout=0.2)
```

### 4.2 回调结果契约（dict）

| 键 | 类型 | 说明 |
|----|------|------|
| `target` | str | 目标地址（构造时传入，回调原样带回） |
| `seq` | int | 自增序号（从 1 开始） |
| `latency` | float/int | 有效延迟 ms；超时/异常为 `None` |
| `avg` | float | 最近 `buffer_size` 次**有效**延迟均值（round 1 位）；无有效样本为 `None` |
| `timeout` | bool | True = 本次无响应/异常 |

### 4.3 周期调度语义（修复后）

`间隔 = interval 秒（自本次发起 ping 到下次发起）`：
```
t0 = monotonic()
发起 ping → 回调 → elapsed = monotonic() - t0
sleep(max(0, interval - elapsed))，按 ≤0.1s 分片以便响应 stop
```
- 调用方禁止在回调内阻塞（回调运行在主线程调度队列）。

---

## 五、业务层 `ping_tool/core/tailscale.py`

```python
TAILSCALE_SERVICE: str   # "Tailscale"

class TailscaleManager:
    @staticmethod
    def is_admin() -> bool
    @staticmethod
    def run_as_admin() -> bool          # 写唯一批处理 + ShellExecuteW(runas)；返回是否弹出
    def restart(self) -> tuple[bool, str]
        # 非管理员 → run_as_admin；管理员 → sc 直连（stop → wait → start）
        # 返回 (是否成功, 用户可读消息)
    def status(self) -> str | None      # tailscale status 输出；异常 → None
```

**行为契约（修复后）**
1. `restart()` 在已具管理员权限时：`net stop` 返回码非 0 → 记录 warning（服务可能已停），继续；`net start` 返回码非 0 → `(False, 详情)`。
2. stop→start 之间的等待时长走配置（默认 3s），禁止硬编码 `time.sleep(3)`。
3. UAC 批处理文件名含 PID/时间戳，避免并发冲突；内容保持 GBK 编码、纯 ASCII 命令。

---

## 六、工具层 `ping_tool/utils/validators.py`

```python
def validate_target(target: str) -> tuple[bool, str]
def sanitize_target(target: str) -> str          # strip + 域名小写
def validate_ipv4(ip: str) -> bool
def validate_ipv6(ip: str) -> bool
def validate_domain(domain: str) -> bool
```

**校验规则（修复后）**
- IPv4：4 段、每段 0-255、**无前导零**（`08.8.8.8` 拒绝）。
- IPv6：支持完整 8 组、`::` 压缩（含 `::1`）、IPv4-mapped（`::ffff:1.2.3.4`）、zone id（`fe80::1%eth0` / `%25`）。
- 域名：完整域名（含 `.`）或**单标签本地名**（`localhost`、`myhost`）；每标签 ≤63、总长 ≤253、仅 `[a-zA-Z0-9-]`。
- 保留地址按**网段语义**判定（先解析成地址对象再判定，等价写法不得绕过）：
  `0.0.0.0/8`、`127.0.0.0/8`、`224.0.0.0/4`、`240.0.0.0/4`、`::/128`、`::1/128`、`ff00::/8`
  以及 IPv4-mapped 形式（`::ffff:127.0.0.1`）拒绝；`fe80::1%12`、`169.254.x.x` 等链路本地仍允许。
- 纯数字单标签（`999`、`12345`）不是合法主机名，拒绝（通常是用户把 IP 写错）。
- 返回 `(bool, 原因)`；校验不得抛异常。

---

## 七、UI 层

### 7.1 `ping_tool/ui/app.py` — PingApp(ctk.CTk)

```python
class PingApp(ctk.CTk):
    _data_manager: DataManager
    _workers: dict[str, PingWorker]          # target → worker
    _cards: dict[str, TargetCard]            # target → card

    def _add_target(self) -> None            # 校验 → 持久化 → 建卡片 → 状态栏反馈
    def _delete_target(self, target: str) -> None
    def _start_all(self) -> None             # 无目标时提示并返回；禁用编辑控件
    def _stop_all(self) -> None              # 停全部 worker、重置卡片、恢复控件
    def _on_ping_result(self, target: str, result: dict) -> None   # 经 self.after(0, ...) 回主线程
    def _on_close(self) -> None              # 停 worker → destroy；异常兜底
    def _restart_tailscale(self) -> None     # 确认框 + 后台线程；线程内 try/except 兜底
```

**约定**
- 所有 worker 回调**必须**通过 `self.after(0, ...)` 回到主线程操作 Tk 控件（线程安全边界）。
- 窗口关闭时：停止全部 worker，随后 `destroy()`；异常不得阻止退出。
- 目标数量上限以 `config.max_targets` 为准。

### 7.2 `ping_tool/ui/components/target_card.py` — 延迟分级

| 延迟 | 颜色（COLORS 键） | 含义 |
|------|-------------------|------|
| < 30 ms | `success` | 优秀 |
| 30–79 ms | `info` | 良好 |
| 80–149 ms | `warning` | 一般 |
| ≥ 150 ms | `error` | 较差 |
| 超时 | `error`（文本「超时」） | 无响应 |

### 7.3 其他组件（状态栏 / Tailscale 卡片）

```python
class StatusBar(ctk.CTkFrame):
    def set_status(self, text: str, color: str | None = None) -> None
    def set_count(self, count: int, pinging: int = 0) -> None

class TailscaleCard(ctk.CTkFrame):
    def update_status(self, success: bool, message: str) -> None   # 恢复按钮 + 显示结果
    def set_status_text(self, text: str, color: str | None = None) -> None
```

---

## 八、入口 `main.py`

```python
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))   # 打包态：工作目录切到 exe 目录
def main():
    logger = setup_logger()
    app = PingApp()
    app.mainloop()                               # 顶层异常 → logger.critical + raise
```

---

## 九、C++ 版契约（`ping-tool-cpp/`，与 Python 对标）

| Python | C++ | 契约要点 |
|--------|-----|----------|
| `PingWorker(target, callback)` | `PingWorker::Start(target, cb)` | 回调携带 `PingResult{target, seq, latency, timeout}`；**周期 = 1s 从发起算起** |
| `PingWorker.stop()` | `PingWorker::Stop()` | **必须**在超时场景快速返回（≤200ms），先终止子进程再 join |
| `PingWorker._ping_once` | `PingWorker::PingOnce` | `WaitForSingleObject` 超时 → `TerminateProcess` → 收尾；禁止 ReadFile 无限阻塞 |
| `DataManager.add/delete` | `DataManager::Add/Delete` | 与 `targets.json` 格式契约一致 |
| `TailscaleManager.restart` | `TailscaleManager::Restart` | stop→wait(3s)→start；UAC 走 `ShellExecuteExW(runas)` |
| 延迟分级 | `LatencyColor/LatencyDot` | `<30/80/150` 四档，与 §7.2 一致 |

> 注：C++ 版当前不可编译（`unsuccessfulbuild`），本次仅做逻辑级修复，编译验证不在本环境能力范围内，需在 Windows + VS 环境回归。

---

## 十、提权层与防火墙层（2026-09-13 新增）

### 10.1 `ping_tool/core/elevation.py`（Tailscale / 防火墙共用）

```python
IS_WINDOWS: bool                    # sys.platform == "win32"

def is_admin() -> bool               # 非 Windows 恒为 False
def run_elevated_batch(command_lines: list[str], name_prefix: str = "pingtool") -> bool
    # 把命令写成唯一命名（含 uuid）的 GBK 批处理写入 %TEMP%，ShellExecuteW(runas) 提权执行
    # 批处理末尾自删；返回是否成功发起提权请求（用户是否确认由系统决定）
```

`TailscaleManager.is_admin()` / `run_as_admin()` 改为委托本模块，对外签名与行为不变。

### 10.2 `ping_tool/core/firewall.py`

```python
STATE_ON / STATE_OFF / STATE_PARTIAL / STATE_UNKNOWN = "on" / "off" / "partial" / "unknown"
STATE_TEXT: dict[str, str]           # 状态 → 中文文案

class FirewallManager:
    def __init__(self)                                # 读取 config.firewall_cmd_timeout
    def query_state(self) -> str                      # on / off / partial / unknown
    @staticmethod
    def _read_registry_states() -> list[bool] | None   # 读 HKLM 三个配置文件的 EnableFirewall
    def disable(self) -> tuple[bool, str, bool]        # (成功, 提示, 是否仅发起提权)
    def enable(self) -> tuple[bool, str, bool]
```

**行为契约**
1. 状态查询读注册表 `HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\{Domain|Standard|Public}Profile\EnableFirewall`，普通用户即可读，**不得**依赖 `netsh show`（未提权会失败）。
2. 三个配置文件全 1 → `on`；全 0 → `off`；混合 → `partial`；读取失败 → `unknown`。
3. 未提权 → `run_elevated_batch(["netsh advfirewall set allprofiles state off|on", "timeout /t 3 /nobreak >nul"], name_prefix="firewall")`，返回 `(True, "已发起…请确认", True)`；提权请求发起失败 → `(False, "需要管理员权限", False)`。
4. 已提权 → 直接 `subprocess.run(["netsh", "advfirewall", "set", "allprofiles", "state", off|on])`，GBK 解码；返回码非 0 → `(False, 含 stderr 的详情, False)`；超时/OSError → `(False, 原因, False)`。
5. 非 Windows 平台：`query_state()` 返回 `unknown`，开关操作返回失败提示，不得抛异常。

### 10.3 UI 层新增

```python
class FirewallCard(ctk.CTkFrame):
    def __init__(self, master, on_action)            # on_action(action)  action ∈ {"off","on","refresh"}
    def set_busy(self, busy: bool, action: str | None = None) -> None
    def update_state(self, state: str, detail: str = "") -> None
```

**约定**
- 卡片的三个动作只上抛回调，实际执行在主窗口后台线程；结果一律经 `_control_queue` 回主线程，
  **禁止**后台线程直接调用 `after` / `configure`。
- `TailscaleCard` 同样新增 `set_busy(busy)`：按钮的「重启中…」状态必须在**确认之后**才设置，
  否则用户取消确认后按钮会永久禁用。
- 卡片行号使用只增不减的计数器 `_next_row`（`row = len(self._cards)` 会在删除中间目标后冲突）。
