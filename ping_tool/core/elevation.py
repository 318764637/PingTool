"""Windows 管理员权限判定与 UAC 提权。

Tailscale 重启、防火墙开关等需要管理员权限的功能共用这里的能力：
判定当前进程是否已提权，以及把一组命令写进临时批处理并以管理员身份运行。
"""
import ctypes
import os
import sys
import uuid

from ..logger import get_logger

logger = get_logger(__name__)

# 非 Windows 平台没有管理员/UAC 概念，统一按「无权限」处理
IS_WINDOWS = sys.platform == "win32"


def _shell32():
    """Windows 下返回 shell32 函数库；非 Windows 返回 None。"""
    if not IS_WINDOWS:
        return None
    try:
        return ctypes.windll.shell32
    except AttributeError:
        return None


def is_admin():
    """当前进程是否以管理员身份运行（非 Windows 恒为 False）。"""
    shell = _shell32()
    if shell is None:
        return False
    try:
        return shell.IsUserAnAdmin() != 0
    except (OSError, AttributeError):
        return False


def run_elevated_batch(command_lines, name_prefix="pingtool"):
    """把命令写成唯一命名的批处理并以管理员身份运行（触发 UAC）。

    Args:
        command_lines: 批处理正文，每个元素一行（须为纯 ASCII 命令）。
        name_prefix: 批处理文件名前缀，便于在 TEMP 目录中辨认来源。

    Returns:
        True 表示提权请求已成功发起（用户是否确认、命令是否成功由系统决定）；
        非 Windows 平台或发起失败返回 False。

    说明：文件名含随机串以避免多实例冲突；批处理执行完会自删，不留残留文件。
    """
    shell = _shell32()
    if shell is None:
        logger.error("非 Windows 平台不支持 UAC 提权")
        return False

    batch = "@echo off\n" + "\n".join(command_lines) + '\ndel "%~f0" >nul 2>&1\n'
    batch_name = f"{name_prefix}_{uuid.uuid4().hex[:8]}.bat"
    batch_path = os.path.join(os.environ.get("TEMP", os.getcwd()), batch_name)
    try:
        # GBK 编码 + 纯 ASCII 命令，避免 cmd 解析 UTF-8 BOM 出错
        with open(batch_path, "w", encoding="gbk") as f:
            f.write(batch)
        shell.ShellExecuteW(None, "runas", batch_path, None, None, 1)
        return True
    except (OSError, AttributeError):
        logger.exception("UAC 提权失败")
        return False
