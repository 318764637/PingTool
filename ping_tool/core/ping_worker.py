import re
import subprocess
import sys
import threading
import time
from collections import deque

from ..config import get_config
from ..logger import get_logger
from ..utils.validators import validate_ipv6

logger = get_logger(__name__)

LATENCY_PATTERN = re.compile(r"(?:时间|time)[=<](\d+)ms")

# CREATE_NO_WINDOW 仅存在于 Windows；非 Windows 下回退为 0
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PingWorker:
    """在独立线程中按固定周期执行 Ping，通过回调返回结果。

    周期语义：从本次发起 ping 到下次发起 = interval 秒
    （ping 自身的耗时计入周期，不额外叠加）。
    """

    def __init__(self, target, callback, interval=None, timeout_ms=None):
        config = get_config()
        self._target = target
        self._callback = callback
        self._interval = float(interval if interval is not None
                               else config.get("ping_interval", 1.0))
        self._timeout_ms = int(timeout_ms if timeout_ms is not None
                               else config.get("ping_timeout", 3000))
        self._buffer_size = int(config.get("buffer_size", 4))
        self._process = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._seq = 0
        self._buffer = deque(maxlen=self._buffer_size)
        # 命令行与目标类型在生命周期内不变，缓存避免每个周期重复校验/构造
        self._cmd = None

    @property
    def is_running(self):
        return self._running

    def start(self):
        if self._running:
            return
        self._running = True
        self._seq = 0
        self._buffer.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_stop(self):
        """仅发送停止信号并终止当前 ping 子进程，不等待线程。

        供调用方批量停止多个 worker 后统一 join，避免逐个同步等待。
        """
        self._running = False
        with self._lock:
            process = self._process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    def stop(self):
        self.request_stop()
        if self._thread:
            self._thread.join(timeout=0.2)

    def _run(self):
        logger.info(f"开始 Ping: {self._target}")
        while self._running:
            cycle_start = time.monotonic()
            try:
                result = self._ping_once()
            except Exception as e:
                logger.error(f"Ping 执行异常: {e}")
                result = self._timeout_result()
            if self._callback:
                try:
                    self._callback(result)
                except Exception as e:
                    logger.error(f"Ping 回调异常: {e}")
            # 等待至下一个周期起点（分片 sleep，保证 stop 可及时响应）
            elapsed = time.monotonic() - cycle_start
            self._sleep_interruptible(self._interval - elapsed)
        logger.info(f"停止 Ping: {self._target}")

    def _sleep_interruptible(self, seconds):
        if seconds <= 0:
            return
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(min(0.1, deadline - time.monotonic()))

    def _build_command(self):
        """构造 ping 命令行：IPv6 目标追加 -6（link-local 带 zone id 时必需）。

        结果缓存：目标与超时在 worker 生命周期内不变。
        """
        if self._cmd is not None:
            return self._cmd
        cmd = ["ping", "-n", "1", "-w", str(self._timeout_ms)]
        if ":" in self._target and validate_ipv6(self._target):
            cmd.append("-6")
        cmd.append(self._target)
        self._cmd = cmd
        return cmd

    def _ping_once(self):
        self._seq += 1
        try:
            with self._lock:
                self._process = subprocess.Popen(
                    self._build_command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=_CREATE_NO_WINDOW,
                )
            stdout, _ = self._process.communicate(
                timeout=(self._timeout_ms / 1000.0) + 2.0
            )
            output = stdout.decode("gbk", errors="replace")

            match = LATENCY_PATTERN.search(output)
            if match:
                latency = int(match.group(1))
                self._buffer.append(latency)
                avg = sum(self._buffer) / len(self._buffer)
                return {
                    "target": self._target,
                    "seq": self._seq,
                    "latency": latency,
                    "avg": round(avg, 1),
                    "timeout": False,
                }
            return self._timeout_result()
        except subprocess.TimeoutExpired:
            self._kill_current_process()
            return self._timeout_result()
        except Exception as e:
            logger.error(f"Ping 异常: {e}")
            return self._timeout_result()
        finally:
            # 清空对已结束子进程的引用，避免 stop() 对僵尸进程重复 terminate
            with self._lock:
                self._process = None

    def _kill_current_process(self):
        """终止卡住的 ping 子进程并回收管道与进程对象。

        仅 kill() 不回收会留下未关闭的管道/未收尸的进程对象；超时是「目标不可达」
        时的常态路径，因此这里补一次 communicate() 完成收尾。
        """
        with self._lock:
            process = self._process
        if process is None:
            return
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.communicate(timeout=1.0)
        except Exception as e:
            # 子进程可能已被回收，或 communicate 再次超时；此处只需保证不抛异常
            logger.debug(f"回收 ping 子进程失败: {e}")

    def _timeout_result(self):
        return {
            "target": self._target,
            "seq": self._seq,
            "latency": None,
            "avg": None,
            "timeout": True,
        }
