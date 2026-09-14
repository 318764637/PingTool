# Ping Tool 架构改进方案

## 1. 模块化拆分方案

### 1.1 目录结构

```
ping_tool/
├── main.py                     # 应用入口
├── config.py                   # 配置管理模块
├── logger.py                   # 日志系统模块
├── data/                       # 数据层
│   ├── __init__.py
│   └── manager.py              # DataManager 数据管理器
├── core/                       # 业务逻辑层
│   ├── __init__.py
│   ├── ping_worker.py          # PingWorker 工作线程
│   └── tailscale.py            # TailscaleManager 服务管理
├── ui/                         # 用户界面层
│   ├── __init__.py
│   ├── app.py                  # PingApp 主窗口
│   ├── components/             # UI 组件
│   │   ├── __init__.py
│   │   ├── target_card.py      # 目标管理卡片组件
│   │   ├── tailscale_card.py   # Tailscale 管理卡片组件
│   │   └── status_bar.py       # 状态栏组件
│   └── styles.py               # 样式常量（颜色、字体）
├── utils/                      # 工具模块
│   ├── __init__.py
│   └── validators.py           # 输入验证工具
├── .gitignore                  # Git 忽略规则
├── README.md                   # 项目说明文档
└── requirements.txt            # 依赖清单
```

### 1.2 模块职责说明

| 模块 | 职责 | 依赖 |
|------|------|------|
| `main.py` | 应用入口，初始化日志系统，启动主窗口 | `logger`, `ui.app` |
| `config.py` | 集中管理所有配置项，支持环境变量覆盖 | 无外部依赖 |
| `logger.py` | 提供统一的日志接口，配置日志格式和输出 | `config` |
| `data/manager.py` | 管理 targets.json 的读写，提供增删查接口 | `logger`, `utils.validators` |
| `core/ping_worker.py` | 在独立线程中执行 Ping 操作，通过回调返回结果 | `logger` |
| `core/tailscale.py` | 管理 Tailscale Windows 服务的重启 | `logger` |
| `ui/app.py` | 主窗口，协调各组件，处理业务逻辑 | `data`, `core`, `ui.components`, `ui.styles` |
| `ui/components/*.py` | 可复用的 UI 组件 | `ui.styles` |
| `ui/styles.py` | 集中管理颜色、字体等样式常量 | `config` |
| `utils/validators.py` | 提供输入验证功能（IP、域名格式验证） | 无外部依赖 |

### 1.3 模块依赖关系图

```
main.py
    ├── logger.py
    └── ui/app.py
            ├── data/manager.py
            │       ├── logger.py
            │       └── utils/validators.py
            ├── core/ping_worker.py
            │       └── logger.py
            ├── core/tailscale.py
            │       └── logger.py
            ├── ui/components/
            │       └── ui/styles.py
            │               └── config.py
            └── ui/styles.py
                    └── config.py
```

---

## 2. 改进任务详细规格

### 任务 1：窗口关闭事件绑定（高优先级）

**任务描述**：绑定窗口关闭事件，确保应用退出时正确释放所有资源（停止 Ping 线程、终止子进程）。

**需要创建/修改的文件**：
- `ui/app.py` - 在 `__init__` 方法中绑定关闭事件

**关键代码结构**：

```python
# ui/app.py - PingApp 类的 __init__ 方法中添加

class PingApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # ... 现有初始化代码 ...
        
        # 绑定窗口关闭事件
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 确保窗口关闭时释放资源
        self._setup_cleanup_hooks()
    
    def _setup_cleanup_hooks(self):
        """设置清理钩子，确保异常退出时也能释放资源。"""
        import atexit
        atexit.register(self._cleanup_resources)
    
    def _cleanup_resources(self):
        """清理所有资源（线程、子进程）。"""
        try:
            self._stop_all()
        except Exception:
            pass
    
    def _on_close(self):
        """窗口关闭事件处理。"""
        self._cleanup_resources()
        self.destroy()
```

**验收标准**：
1. 点击窗口关闭按钮时，所有 Ping 线程被正确停止
2. 所有 Ping 子进程被终止
3. 应用进程完全退出，无残留
4. 异常退出时资源也能被正确释放

---

### 任务 2：添加日志系统（高优先级）

**任务描述**：实现统一的日志系统，支持文件日志和控制台输出，便于生产环境问题排查。

**需要创建/修改的文件**：
- `logger.py` - 新建日志模块
- `main.py` - 初始化日志系统
- 所有模块 - 添加日志记录

**关键代码结构**：

```python
# logger.py

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import LOG_CONFIG


def setup_logger(name: str = "ping_tool") -> logging.Logger:
    """
    配置并返回应用日志器。
    
    Args:
        name: 日志器名称
        
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, LOG_CONFIG["level"]))
    
    # 日志格式
    formatter = logging.Formatter(
        fmt=LOG_CONFIG["format"],
        datefmt=LOG_CONFIG["date_format"]
    )
    
    # 控制台处理器
    if LOG_CONFIG["console_output"]:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器（带轮转）
    if LOG_CONFIG["file_output"]:
        log_dir = os.path.dirname(LOG_CONFIG["file_path"])
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            filename=LOG_CONFIG["file_path"],
            maxBytes=LOG_CONFIG["max_file_size"],
            backupCount=LOG_CONFIG["backup_count"],
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, LOG_CONFIG["file_level"]))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# 全局日志器实例
logger = setup_logger()
```

**日志使用示例**：

```python
# 在各模块中使用
from logger import logger

class DataManager:
    @classmethod
    def load(cls) -> list:
        logger.debug("正在加载目标列表...")
        # ... 业务逻辑 ...
        logger.info(f"成功加载 {len(targets)} 个目标")
        return targets
    
    @classmethod
    def save(cls, targets: list) -> bool:
        logger.info(f"正在保存 {len(targets)} 个目标...")
        try:
            # ... 保存逻辑 ...
            logger.info("目标列表保存成功")
            return True
        except Exception as e:
            logger.error(f"保存目标列表失败: {e}", exc_info=True)
            return False
```

**验收标准**：
1. 日志同时输出到控制台和文件
2. 日志文件自动轮转，单个文件不超过 5MB，保留 3 个备份
3. 日志包含时间戳、级别、模块名、行号等信息
4. 生产环境可配置日志级别

---

### 任务 3：单文件拆分（高优先级）

**任务描述**：将 744 行的单文件拆分为多个模块，提高可维护性。

**需要创建的文件**：

| 文件 | 从原文件提取的代码 | 行数估计 |
|------|-------------------|---------|
| `config.py` | 配置常量、颜色、字体 | ~80 行 |
| `data/__init__.py` | 包初始化 | ~5 行 |
| `data/manager.py` | DataManager 类 | ~70 行 |
| `core/__init__.py` | 包初始化 | ~5 行 |
| `core/ping_worker.py` | PingWorker 类 | ~100 行 |
| `core/tailscale.py` | TailscaleManager 类 | ~80 行 |
| `ui/__init__.py` | 包初始化 | ~5 行 |
| `ui/styles.py` | 样式常量、辅助函数 | ~40 行 |
| `ui/components/__init__.py` | 包初始化 | ~5 行 |
| `ui/components/target_card.py` | 目标管理卡片组件 | ~120 行 |
| `ui/components/tailscale_card.py` | Tailscale 卡片组件 | ~50 行 |
| `ui/components/status_bar.py` | 状态栏组件 | ~30 行 |
| `ui/app.py` | PingApp 主窗口类 | ~200 行 |
| `utils/__init__.py` | 包初始化 | ~5 行 |
| `utils/validators.py` | 输入验证函数 | ~50 行 |
| `main.py` | 应用入口 | ~20 行 |

**验收标准**：
1. 每个模块职责单一，代码行数控制在 200 行以内
2. 模块间通过明确的接口交互
3. 功能与原代码完全一致
4. 所有导入路径正确

---

### 任务 4：添加 .gitignore（高优先级）

**任务描述**：创建 .gitignore 文件，防止构建产物和临时文件被误提交。

**需要创建的文件**：
- `.gitignore`

**文件内容**：

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
env/
ENV/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# PyInstaller
*.spec
*.exe
*.dll
*.dylib

# Application
targets.json
*.log
logs/

# OS
.DS_Store
Thumbs.db
desktop.ini

# Temp
*.tmp
*.bak
*.cache
```

**验收标准**：
1. 构建产物（dist/、build/、*.spec）被忽略
2. 日志文件被忽略
3. 数据文件 targets.json 可选择性忽略（建议保留空数组版本）
4. IDE 配置文件被忽略

---

### 任务 5：配置外部化（中优先级）

**任务描述**：将硬编码的配置项提取到独立配置文件，支持环境变量覆盖。

**需要创建/修改的文件**：
- `config.py` - 新建配置模块
- `ui/styles.py` - 引用配置

**关键代码结构**：

```python
# config.py

import os
from typing import Any


class Config:
    """应用配置管理器，支持默认值和环境变量覆盖。"""
    
    # 配置默认值
    _defaults = {
        # 窗口配置
        "window": {
            "title": "Ping Tool",
            "width": 500,
            "height": 550,
            "min_width": 440,
            "min_height": 500,
        },
        
        # Ping 配置
        "ping": {
            "interval": 1.0,          # Ping 间隔（秒）
            "timeout": 3000,           # Ping 超时（毫秒）
            "max_targets": 20,         # 最大目标数量
            "buffer_size": 4,          # 结果缓冲区大小
        },
        
        # 日志配置
        "log": {
            "level": "INFO",
            "file_output": True,
            "console_output": True,
            "file_path": "logs/ping_tool.log",
            "file_level": "DEBUG",
            "max_file_size": 5 * 1024 * 1024,  # 5MB
            "backup_count": 3,
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
            "date_format": "%Y-%m-%d %H:%M:%S",
        },
        
        # UI 样式配置
        "style": {
            "appearance_mode": "light",
            "color_theme": "blue",
            "font_family": "Segoe UI Variable",
        },
        
        # Tailscale 配置
        "tailscale": {
            "service_name": "Tailscale",
            "restart_timeout": 30,
            "stop_wait_time": 3,
        },
        
        # 数据文件配置
        "data": {
            "filename": "targets.json",
            "encoding": "utf-8",
        },
    }
    
    _instance = None
    _config = None
    
    def __new__(cls):
        """单例模式。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置，支持环境变量覆盖。"""
        import json
        
        self._config = self._defaults.copy()
        
        # 尝试从配置文件加载
        config_file = os.environ.get("PING_TOOL_CONFIG", "config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                self._merge_config(self._config, file_config)
            except Exception:
                pass
        
        # 环境变量覆盖（格式：PING_TOOL_SECTION_KEY）
        for section, values in self._config.items():
            if isinstance(values, dict):
                for key, default_value in values.items():
                    env_key = f"PING_TOOL_{section.upper()}_{key.upper()}"
                    env_value = os.environ.get(env_key)
                    if env_value is not None:
                        # 尝试转换类型
                        values[key] = self._convert_value(env_value, default_value)
    
    def _merge_config(self, base: dict, override: dict):
        """递归合并配置字典。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _convert_value(self, value: str, reference: Any) -> Any:
        """根据参考值的类型转换字符串值。"""
        if isinstance(reference, bool):
            return value.lower() in ("true", "1", "yes")
        elif isinstance(reference, int):
            return int(value)
        elif isinstance(reference, float):
            return float(value)
        return value
    
    def get(self, section: str, key: str = None, default: Any = None) -> Any:
        """获取配置值。"""
        if key is None:
            return self._config.get(section, default)
        section_config = self._config.get(section, {})
        return section_config.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        return self._config[key]


# 全局配置实例
config = Config()

# 便捷访问
WINDOW_CONFIG = config.get("window")
PING_CONFIG = config.get("ping")
LOG_CONFIG = config.get("log")
STYLE_CONFIG = config.get("style")
TAILSCALE_CONFIG = config.get("tailscale")
DATA_CONFIG = config.get("data")
```

**验收标准**：
1. 所有硬编码的配置项都可配置
2. 支持环境变量覆盖
3. 支持外部配置文件（config.json）
4. 配置有合理的默认值

---

### 任务 6：输入验证增强（中优先级）

**任务描述**：增强输入验证，防止添加无效目标。

**需要创建/修改的文件**：
- `utils/validators.py` - 新建验证模块
- `data/manager.py` - 集成验证
- `ui/components/target_card.py` - 显示验证错误

**关键代码结构**：

```python
# utils/validators.py

import re
from typing import Tuple


class InputValidator:
    """输入验证器，提供 IP 地址和域名的格式验证。"""
    
    # IPv4 正则表达式
    IPV4_PATTERN = re.compile(
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
        r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )
    
    # IPv6 正则表达式（简化版）
    IPV6_PATTERN = re.compile(
        r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$"
    )
    
    # 域名正则表达式
    DOMAIN_PATTERN = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)"
        r"+[a-zA-Z]{2,}$"
    )
    
    # 保留地址列表
    RESERVED_ADDRESSES = [
        "0.0.0.0",
        "255.255.255.255",
    ]
    
    @classmethod
    def validate_target(cls, target: str) -> Tuple[bool, str]:
        """
        验证目标地址是否有效。
        
        Args:
            target: 要验证的目标地址
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息或"")
        """
        target = target.strip()
        
        # 空值检查
        if not target:
            return False, "目标地址不能为空"
        
        # 长度检查
        if len(target) > 255:
            return False, "目标地址过长（最大 255 字符）"
        
        # 检查是否为保留地址
        if target in cls.RESERVED_ADDRESSES:
            return False, f"'{target}' 是保留地址，不能使用"
        
        # 验证格式
        if cls.IPV4_PATTERN.match(target):
            return True, ""
        elif cls.IPV6_PATTERN.match(target):
            return True, ""
        elif cls.DOMAIN_PATTERN.match(target):
            # 域名额外检查
            if len(target) > 253:
                return False, "域名过长（最大 253 字符）"
            return True, ""
        else:
            return False, "无效的 IP 地址或域名格式"
    
    @classmethod
    def sanitize_target(cls, target: str) -> str:
        """
        清理目标地址（去除首尾空格，转小写域名）。
        
        Args:
            target: 原始目标地址
            
        Returns:
            清理后的目标地址
        """
        target = target.strip()
        
        # 如果是域名，转为小写
        if not cls.IPV4_PATTERN.match(target) and not cls.IPV6_PATTERN.match(target):
            target = target.lower()
        
        return target


# 便捷函数
def validate_target(target: str) -> Tuple[bool, str]:
    """验证目标地址。"""
    return InputValidator.validate_target(target)


def sanitize_target(target: str) -> str:
    """清理目标地址。"""
    return InputValidator.sanitize_target(target)
```

**验收标准**：
1. 验证 IP 地址格式（IPv4、IPv6）
2. 验证域名格式
3. 阻止添加保留地址
4. 提供清晰的错误提示
5. 自动清理输入（去除空格、域名小写）

---

### 任务 7：目标数量限制（中优先级）

**任务描述**：限制最大目标数量，防止性能问题。

**需要创建/修改的文件**：
- `config.py` - 已包含 max_targets 配置
- `data/manager.py` - 添加数量检查
- `ui/components/target_card.py` - 显示数量限制提示

**关键代码结构**：

```python
# data/manager.py

from config import PING_CONFIG
from logger import logger
from utils.validators import validate_target, sanitize_target


class DataManager:
    """管理 targets.json 的读写，提供增删查接口。"""
    
    MAX_TARGETS = PING_CONFIG.get("max_targets", 20)
    
    @classmethod
    def add(cls, target: str) -> Tuple[bool, str]:
        """
        添加一个目标。
        
        Args:
            target: 目标地址
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 清理输入
        target = sanitize_target(target)
        
        # 验证格式
        is_valid, error_msg = validate_target(target)
        if not is_valid:
            logger.warning(f"目标验证失败: {target} - {error_msg}")
            return False, error_msg
        
        # 加载现有目标
        targets = cls.load()
        
        # 检查是否已存在
        if target in targets:
            logger.info(f"目标已存在: {target}")
            return False, f"'{target}' 已在列表中"
        
        # 检查数量限制
        if len(targets) >= cls.MAX_TARGETS:
            logger.warning(f"目标数量已达上限: {cls.MAX_TARGETS}")
            return False, f"目标数量已达上限（最多 {cls.MAX_TARGETS} 个）"
        
        # 添加并保存
        targets.append(target)
        if cls.save(targets):
            logger.info(f"成功添加目标: {target}")
            return True, f"已添加: {target}"
        else:
            logger.error(f"保存目标失败: {target}")
            return False, "保存失败，请检查文件权限"
```

**验收标准**：
1. 最大目标数量可配置（默认 20）
2. 达到上限时给出明确提示
3. 提示信息包含当前限制数量

---

### 任务 8：添加 README.md（中优先级）

**任务描述**：创建项目说明文档，帮助新用户快速上手。

**需要创建的文件**：
- `README.md`

**文件结构**：

```markdown
# Ping Tool

一个基于 Python 和 CustomTkinter 的 Windows 桌面 Ping 工具，支持多目标同时 Ping 和 Tailscale 服务管理。

## 功能特性

- 🎯 多目标同时 Ping
- 📊 实时延迟可视化
- 🔄 Tailscale 服务一键重启
- 💾 目标列表持久化存储
- 🎨 现代化 Win11 风格界面

## 系统要求

- Windows 10/11
- Python 3.9+
- Tailscale（可选，用于 Tailscale 管理功能）

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行程序

```bash
python main.py
```

### 打包为 EXE

```bash
pyinstaller PingTool.spec
```

## 使用说明

### 添加目标

1. 在输入框中输入 IP 地址或域名
2. 点击「添加」按钮或按回车键
3. 目标将显示在列表中

### 开始 Ping

1. 点击「开始 Ping 全部」按钮
2. 所有目标将同时开始 Ping
3. 延迟结果以彩色方块显示：
   - 🟢 绿色：< 30ms（优秀）
   - 🔵 蓝色：30-80ms（良好）
   - 🟡 黄色：80-150ms（一般）
   - 🔴 红色：> 150ms（较差）
   - ⚫ 黑色：超时

### Tailscale 管理

- 点击「重启 Tailscale」按钮
- 需要管理员权限
- 首次使用会弹出 UAC 确认窗口

## 配置说明

应用支持通过环境变量或配置文件进行自定义：

### 环境变量

```bash
# 设置最大目标数量
PING_TOOL_PING_MAX_TARGETS=30

# 设置日志级别
PING_TOOL_LOG_LEVEL=DEBUG

# 设置窗口标题
PING_TOOL_WINDOW_TITLE="我的 Ping 工具"
```

### 配置文件

创建 `config.json` 文件：

```json
{
  "window": {
    "title": "Ping Tool",
    "width": 600,
    "height": 700
  },
  "ping": {
    "interval": 2.0,
    "max_targets": 30
  },
  "log": {
    "level": "DEBUG"
  }
}
```

## 目录结构

```
ping_tool/
├── main.py                 # 应用入口
├── config.py               # 配置管理
├── logger.py               # 日志系统
├── data/                   # 数据层
├── core/                   # 业务逻辑层
├── ui/                     # 用户界面层
├── utils/                  # 工具模块
├── .gitignore              # Git 忽略规则
├── README.md               # 本文档
└── requirements.txt        # 依赖清单
```

## 开发说明

### 项目结构

项目采用分层架构设计：

- **数据层** (`data/`) - 负责数据持久化
- **业务层** (`core/`) - 负责核心业务逻辑
- **界面层** (`ui/`) - 负责用户交互
- **工具层** (`utils/`) - 提供通用工具函数

### 添加新功能

1. 在相应层级创建新模块
2. 遵循现有的代码风格
3. 添加适当的日志记录
4. 更新配置（如需要）
5. 更新本文档

## 常见问题

### Q: 为什么需要管理员权限？

A: 重启 Tailscale 服务需要管理员权限。程序会自动检测并请求提升权限。

### Q: 目标数量有限制吗？

A: 默认最多 20 个目标，可通过配置修改。

### Q: 日志文件在哪里？

A: 日志文件位于 `logs/ping_tool.log`，自动轮转，单个文件最大 5MB。

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交 Issue。
```

**验收标准**：
1. 包含完整的功能说明
2. 提供清晰的安装和使用指南
3. 包含配置说明
4. 包含常见问题解答
5. 文档格式规范，易于阅读

---

## 3. 执行顺序

### 3.1 依赖关系分析

```
任务4（.gitignore）
    └── 无依赖，可立即执行

任务1（窗口关闭事件）
    └── 依赖：任务3（模块拆分）

任务2（日志系统）
    └── 依赖：任务5（配置外部化）

任务3（模块拆分）
    └── 依赖：任务5（配置外部化）

任务5（配置外部化）
    └── 无依赖，可立即执行

任务6（输入验证）
    └── 依赖：任务3（模块拆分）

任务7（目标数量限制）
    └── 依赖：任务5（配置外部化）、任务6（输入验证）

任务8（README.md）
    └── 无依赖，可立即执行
```

### 3.2 建议执行顺序

#### 第一阶段：基础准备（可并行）
1. **任务4** - 创建 .gitignore
2. **任务8** - 创建 README.md

#### 第二阶段：配置与日志（可并行）
3. **任务5** - 配置外部化（创建 config.py）
4. **任务2** - 日志系统（创建 logger.py）

#### 第三阶段：模块拆分
5. **任务3** - 单文件拆分
   - 创建目录结构
   - 提取各模块代码
   - 更新导入路径

#### 第四阶段：功能增强（可并行）
6. **任务1** - 窗口关闭事件绑定
7. **任务6** - 输入验证增强
8. **任务7** - 目标数量限制

#### 第五阶段：验证与优化
9. 功能测试
10. 性能优化
11. 文档完善

### 3.3 并行执行矩阵

```
阶段   任务    可并行任务    预计时间
──────────────────────────────────────
1      4,8     是          0.5天
2      5,2     是          1天
3      5       否          1.5天
4      1,6,7   是          1天
5      -       -           1天
──────────────────────────────────────
总计                        5天
```

---

## 4. 配置文件模板

### 4.1 .gitignore

（见任务4）

### 4.2 config.py

（见任务5）

### 4.3 README.md

（见任务8）

---

## 5. 日志系统设计

### 5.1 日志级别定义

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| DEBUG | 详细的调试信息 | 函数调用参数、返回值 |
| INFO | 一般运行信息 | 目标添加/删除、Ping 开始/停止 |
| WARNING | 警告信息 | 输入验证失败、达到数量限制 |
| ERROR | 错误信息 | 文件读写失败、网络错误 |
| CRITICAL | 严重错误 | 应用崩溃、无法启动 |

### 5.2 日志格式

```
格式：%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s

示例：
2026-07-31 14:30:25 [INFO] data.manager:45 - 成功加载 5 个目标
2026-07-31 14:30:26 [WARNING] utils.validators:78 - 目标验证失败: 999.999.999 - 无效的 IP 地址格式
2026-07-31 14:30:27 [ERROR] data.manager:62 - 保存目标列表失败: PermissionError
```

### 5.3 日志文件配置

| 配置项 | 默认值 | 说明 |
|--------|-------|------|
| file_path | logs/ping_tool.log | 日志文件路径 |
| max_file_size | 5MB | 单个日志文件最大大小 |
| backup_count | 3 | 保留的备份文件数量 |
| file_level | DEBUG | 文件日志级别 |
| console_level | INFO | 控制台日志级别 |
| encoding | utf-8 | 日志文件编码 |

### 5.4 日志文件轮转策略

```
logs/
├── ping_tool.log          # 当前日志文件
├── ping_tool.log.1        # 最近的备份
├── ping_tool.log.2        # 较早的备份
└── ping_tool.log.3        # 最早的备份（将被删除）
```

当 `ping_tool.log` 达到 5MB 时：
1. `ping_tool.log.3` 被删除
2. `ping_tool.log.2` 重命名为 `ping_tool.log.3`
3. `ping_tool.log.1` 重命名为 `ping_tool.log.2`
4. `ping_tool.log` 重命名为 `ping_tool.log.1`
5. 创建新的 `ping_tool.log`

---

## 6. 风险与注意事项

### 6.1 兼容性风险
- 模块拆分可能引入导入路径错误
- 建议：拆分后进行全面测试

### 6.2 性能风险
- 日志记录可能影响性能
- 建议：生产环境使用 WARNING 或 INFO 级别

### 6.3 数据迁移
- 配置外部化后，旧的 targets.json 格式需兼容
- 建议：保持数据格式不变

### 6.4 依赖管理
- 确保 requirements.txt 包含所有依赖
- 建议：使用虚拟环境进行开发

---

## 7. 测试建议

### 7.1 单元测试
- 测试 InputValidator 的各种输入情况
- 测试 DataManager 的读写操作
- 测试 Config 的配置加载

### 7.2 集成测试
- 测试模块间的交互
- 测试日志系统的完整流程

### 7.3 端到端测试
- 测试完整的 Ping 流程
- 测试窗口关闭时的资源释放
- 测试配置的生效情况

---

## 8. 总结

本改进方案针对当前项目的 8 个问题，提供了详细的解决方案：

1. **高优先级问题**：窗口关闭事件、日志系统、模块拆分、.gitignore
2. **中优先级问题**：配置外部化、输入验证、目标数量限制、README

通过分阶段实施，预计 5 个工作日可完成所有改进。改进后的项目将具有更好的可维护性、可扩展性和用户体验。