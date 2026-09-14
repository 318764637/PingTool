"""PingWorker 单元测试。

核心逻辑测试通过 mock subprocess.Popen 完成（避免真实网络依赖）；
周期调度测试通过替换 _ping_once 实现。
"""
import subprocess
import time
from unittest import mock

import pytest

from ping_tool.core.ping_worker import PingWorker


class FakeProcess:
    """模拟 subprocess.Popen 返回对象。"""

    def __init__(self, output: bytes, raise_timeout=False):
        self._output = output
        self._raise_timeout = raise_timeout
        self.terminated = False
        self.killed = False
        self.communicated = False

    def communicate(self, timeout=None):
        self.communicated = True
        if self._raise_timeout:
            raise subprocess.TimeoutExpired(cmd="ping", timeout=timeout)
        return self._output, b""

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def run_ping_once(target, output: bytes, raise_timeout=False):
    """在 mock Popen 下执行一次 _ping_once。"""
    worker = PingWorker(target, callback=None, interval=0.1, timeout_ms=3000)
    with mock.patch(
        "ping_tool.core.ping_worker.subprocess.Popen",
        return_value=FakeProcess(output, raise_timeout),
    ):
        return worker._ping_once(), worker


class TestBuildCommand:
    def _cmd(self, target):
        worker = PingWorker(target, None, interval=0.1, timeout_ms=3000)
        return worker._build_command()

    def test_ipv4(self):
        assert self._cmd("8.8.8.8") == ["ping", "-n", "1", "-w", "3000", "8.8.8.8"]

    def test_ipv6_adds_flag(self):
        cmd = self._cmd("fe80::1%12")
        assert cmd == ["ping", "-n", "1", "-w", "3000", "-6", "fe80::1%12"]

    def test_ipv6_loopback(self):
        cmd = self._cmd("::1")
        assert "-6" in cmd

    def test_domain_no_flag(self):
        cmd = self._cmd("baidu.com")
        assert "-6" not in cmd

    def test_uses_config_timeout(self):
        worker = PingWorker("8.8.8.8", None, interval=0.1, timeout_ms=1500)
        cmd = worker._build_command()
        assert "-w" in cmd and cmd[cmd.index("-w") + 1] == "1500"


class TestPingOnce:
    def test_parse_chinese(self):
        out = "来自 8.8.8.8 的回复: 字节=32 时间=23ms TTL=117".encode("gbk")
        result, worker = run_ping_once("8.8.8.8", out)
        assert result["timeout"] is False
        assert result["latency"] == 23
        assert result["seq"] == 1

    def test_parse_english(self):
        out = b"Reply from 8.8.8.8: bytes=32 time=10ms TTL=117"
        result, _ = run_ping_once("8.8.8.8", out)
        assert result["latency"] == 10
        assert result["timeout"] is False

    def test_parse_sub_ms(self):
        out = "Reply from 127.0.0.1: time<1ms".encode("gbk")
        result, _ = run_ping_once("127.0.0.1", out)
        assert result["timeout"] is False
        assert result["latency"] == 1  # 正则将 <1ms 解析为 1

    def test_timeout_output(self):
        out = "请求超时。".encode("gbk")
        result, _ = run_ping_once("192.0.2.1", out)
        assert result["timeout"] is True
        assert result["latency"] is None
        assert result["avg"] is None

    def test_communicate_timeout_kills_process(self):
        fake = FakeProcess(b"", raise_timeout=True)
        worker = PingWorker("192.0.2.1", None, interval=0.1, timeout_ms=3000)
        with mock.patch(
            "ping_tool.core.ping_worker.subprocess.Popen", return_value=fake
        ):
            result = worker._ping_once()
        assert result["timeout"] is True
        assert fake.killed
        # 结束后对子进程的引用被清理
        assert worker._process is None

    def test_process_reference_cleared(self):
        _, worker = run_ping_once("8.8.8.8", b"Reply: time=5ms")
        assert worker._process is None


class TestLifecycle:
    def test_start_is_idempotent(self):
        worker = PingWorker("8.8.8.8", None, interval=0.05, timeout_ms=100)
        worker._ping_once = lambda: {"timeout": True}
        worker.start()
        t = worker._thread
        worker.start()
        assert worker._thread is t  # 不重复创建线程
        worker.stop()

    def test_request_stop_sets_flag_and_terminates(self):
        worker = PingWorker("8.8.8.8", None, interval=0.05, timeout_ms=100)
        worker._ping_once = lambda: {"timeout": True}
        worker.start()
        worker.request_stop()
        assert worker.is_running is False
        worker.stop()
        assert worker._thread is not None and not worker._thread.is_alive()

    def test_periodic_scheduling_counts_interval(self):
        """周期 = interval：0.2s 间隔下，0.45s 内应产生约 2 次回调。"""
        results = []
        worker = PingWorker("8.8.8.8", results.append, interval=0.2, timeout_ms=100)
        worker._ping_once = lambda: {
            "target": "8.8.8.8", "seq": 0, "latency": 1, "avg": 1.0, "timeout": False,
        }
        worker.start()
        time.sleep(0.45)
        worker.stop()
        assert 2 <= len(results) <= 3

    def test_callback_exception_is_swallowed(self):
        def boom(_result):
            raise RuntimeError("callback failed")

        worker = PingWorker("8.8.8.8", boom, interval=0.05, timeout_ms=100)
        worker._ping_once = lambda: {
            "target": "8.8.8.8", "seq": 0, "latency": 1, "avg": 1.0, "timeout": False,
        }
        worker.start()
        time.sleep(0.12)
        worker.stop()  # 不应抛异常

    def test_stop_during_ping_does_not_block_long(self):
        """stop 在 ping 卡住时应尽快返回（join timeout=0.2）。"""
        worker = PingWorker("8.8.8.8", None, interval=1.0, timeout_ms=5000)
        # 模拟长时间阻塞的 ping
        worker._ping_once = lambda: time.sleep(10) or {"timeout": True}
        worker.start()
        time.sleep(0.05)
        started = time.monotonic()
        worker.stop()
        elapsed = time.monotonic() - started
        assert elapsed < 1.0  # 不应等待 10s
