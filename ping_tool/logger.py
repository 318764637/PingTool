import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import get_config, APP_NAME

_configured = False


def setup_logger(name=None, log_file=None):
    """配置并返回应用日志器（幂等）。

    handler 挂载到 root logger，使各模块通过 get_logger(__name__)
    得到的子 logger 都能沿 propagate 链统一输出到文件与控制台。

    幂等判断使用本模块 `_configured` 标志而非 `root.handlers`：
    若第三方库先向 root logger 挂过 handler，后者会导致配置被误跳过。
    """
    global _configured
    if _configured:
        return logging.getLogger(name or APP_NAME)

    config = get_config()

    if log_file is None:
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        log_dir = Path(base) / APP_NAME / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "pingtool.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.get("log_max_bytes", 5 * 1024 * 1024),
        backupCount=config.get("log_backup_count", 3),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    root.addHandler(file_handler)

    # 打包为 --windowed 时 sys.stdout/sys.stderr 均为 None，此时挂控制台 handler
    # 会让每条日志都在 emit 内部抛异常再被 logging 静默吞掉。仅在存在输出流时挂载。
    console_stream = sys.stdout if sys.stdout is not None else sys.stderr
    if console_stream is not None:
        console_handler = logging.StreamHandler(console_stream)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    _configured = True
    return logging.getLogger(name or APP_NAME)


def get_logger(name=None):
    return logging.getLogger(name or APP_NAME)
