"""Windows 防火墙开关管理（netsh advfirewall）。

关闭/开启防火墙需要管理员权限：已提权时直接执行 netsh 并回报真实结果；
未提权时通过 UAC 提权批处理执行。状态查询走注册表（普通用户可读，
无需提权），因此在未提权的常态下也能显示当前状态。
"""
import subprocess
import sys

from ..config import get_config
from ..logger import get_logger
from .elevation import is_admin, run_elevated_batch

logger = get_logger(__name__)

# 注册表中的防火墙配置节点（Domain / Standard / Public 三个配置文件）
_REG_PATH = (
    r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters"
    r"\FirewallPolicy\{profile}Profile"
)
_REG_PROFILES = ("Domain", "Standard", "Public")
_REG_VALUE = "EnableFirewall"

STATE_ON = "on"
STATE_OFF = "off"
STATE_PARTIAL = "partial"
STATE_UNKNOWN = "unknown"

STATE_TEXT = {
    STATE_ON: "已开启",
    STATE_OFF: "已关闭",
    STATE_PARTIAL: "部分开启",
    STATE_UNKNOWN: "未知",
}


class FirewallManager:
    """读写 Windows 防火墙状态，支持 UAC 提权开关。"""

    def __init__(self):
        config = get_config()
        self._cmd_timeout = float(config.get("firewall_cmd_timeout", 30))

    @staticmethod
    def is_admin():
        return is_admin()

    def query_state(self):
        """查询防火墙状态：on / off / partial / unknown。

        读注册表而非 `netsh show`，因为后者在未提权时会因权限不足失败，
        而注册表键普通用户即可读取。
        """
        states = self._read_registry_states()
        if states is None:
            return STATE_UNKNOWN
        if all(states):
            return STATE_ON
        if not any(states):
            return STATE_OFF
        return STATE_PARTIAL

    @staticmethod
    def _read_registry_states():
        """返回三个配置文件的开关列表；非 Windows 或读取失败返回 None。"""
        if sys.platform != "win32":
            return None
        try:
            import winreg
        except ImportError:
            return None

        states = []
        for profile in _REG_PROFILES:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, _REG_PATH.format(profile=profile)
                ) as key:
                    value, _ = winreg.QueryValueEx(key, _REG_VALUE)
            except OSError as e:
                logger.debug(f"读取防火墙注册表失败: {e}")
                return None
            states.append(int(value) != 0)
        return states

    def disable(self):
        """关闭所有配置文件（Domain/Standard/Public）的防火墙。"""
        return self._set_state(False)

    def enable(self):
        """开启所有配置文件（Domain/Standard/Public）的防火墙。"""
        return self._set_state(True)

    def _set_state(self, enabled):
        """执行开关操作。

        Returns:
            (success, message, elevated)：elevated 为 True 表示只是发起了 UAC
            提权请求，命令结果未知（用户可能还没确认），调用方可稍后复查状态。
        """
        state = "on" if enabled else "off"
        action = "开启" if enabled else "关闭"
        netsh_args = ["netsh", "advfirewall", "set", "allprofiles", "state", state]

        if not is_admin():
            # 未提权：交给 UAC 批处理执行，等待片刻让三个配置文件逐个生效
            launched = run_elevated_batch(
                [" ".join(netsh_args), "timeout /t 3 /nobreak >nul"],
                name_prefix="firewall",
            )
            if launched:
                return (
                    True,
                    f"已发起{action}请求，请在弹出的管理员窗口中确认",
                    True,
                )
            return False, "需要管理员权限", False

        try:
            logger.info(f"正在{action} Windows 防火墙...")
            result = subprocess.run(
                netsh_args,
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace",
                timeout=self._cmd_timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            logger.error("防火墙操作超时")
            return False, "防火墙操作超时", False
        except OSError as e:
            logger.error(f"防火墙操作失败: {e}")
            return False, f"防火墙操作失败: {e}", False

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            logger.error(f"防火墙{action}失败: {detail}")
            return False, f"防火墙{action}失败: {detail}", False

        logger.info(f"Windows 防火墙已{action}")
        return True, f"防火墙已{action}", False
