import subprocess
import time

from ..config import get_config
from ..logger import get_logger
from .elevation import is_admin, run_elevated_batch

logger = get_logger(__name__)

TAILSCALE_SERVICE = "Tailscale"
TAILSCALE_EXE = "tailscale"


class TailscaleManager:
    """管理 Tailscale Windows 服务的重启，支持 UAC 提权。"""

    def __init__(self):
        config = get_config()
        self._stop_wait = float(config.get("tailscale_stop_wait", 3))
        self._cmd_timeout = float(config.get("tailscale_cmd_timeout", 30))

    @staticmethod
    def is_admin():
        return is_admin()

    def run_as_admin(self):
        wait_sec = max(1, int(self._stop_wait))
        # 等待时长走配置，与已提权路径保持一致
        return run_elevated_batch(
            [
                f"net stop {TAILSCALE_SERVICE}",
                f"timeout /t {wait_sec} /nobreak >nul",
                f"net start {TAILSCALE_SERVICE}",
                f"timeout /t {wait_sec} /nobreak >nul",
            ],
            name_prefix="tailscale_restart",
        )

    def restart(self):
        if not self.is_admin():
            success = self.run_as_admin()
            if success:
                return True, "已弹出管理员确认窗口，请在弹出的窗口中确认并等待完成"
            return False, "需要管理员权限"
        try:
            logger.info("正在重启 Tailscale 服务...")

            result = subprocess.run(
                ["net", "stop", TAILSCALE_SERVICE],
                capture_output=True,
                text=True,
                timeout=self._cmd_timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            if result.returncode != 0:
                # 服务可能本就处于停止状态，记录但不中断流程
                logger.warning(
                    f"停止服务输出: {(result.stderr or result.stdout).strip()}"
                )

            time.sleep(self._stop_wait)

            result = subprocess.run(
                ["net", "start", TAILSCALE_SERVICE],
                capture_output=True,
                text=True,
                timeout=self._cmd_timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            if result.returncode != 0:
                logger.error(f"启动服务失败: {result.stderr}")
                return False, f"启动服务失败: {result.stderr}"

            logger.info("Tailscale 服务重启成功")
            return True, "服务重启成功"

        except subprocess.TimeoutExpired:
            logger.error("服务操作超时")
            return False, "服务操作超时"
        except Exception as e:
            logger.error(f"重启服务异常: {e}")
            return False, f"重启失败: {e}"

    def status(self):
        try:
            result = subprocess.run(
                [TAILSCALE_EXE, "status"],
                capture_output=True,
                text=True,
                timeout=self._cmd_timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except Exception as e:
            logger.debug(f"查询 Tailscale 状态失败: {e}")
            return None
