"""FirewallManager 单元测试。

全部通过 mock 隔离：不实际调用 netsh、不触发 UAC、不改动系统防火墙。
状态查询（读注册表）是只读操作，允许真实执行，只断言返回值在合法集合内。
"""
import subprocess
from unittest import mock

import pytest

from ping_tool.core import firewall
from ping_tool.core.firewall import (
    FirewallManager,
    STATE_OFF,
    STATE_ON,
    STATE_PARTIAL,
    STATE_UNKNOWN,
)


class TestQueryState:
    def test_real_query_returns_known_state(self):
        assert FirewallManager().query_state() in {
            STATE_ON, STATE_OFF, STATE_PARTIAL, STATE_UNKNOWN
        }

    def test_all_profiles_on(self, monkeypatch):
        monkeypatch.setattr(
            FirewallManager, "_read_registry_states",
            staticmethod(lambda: [True, True, True]),
        )
        assert FirewallManager().query_state() == STATE_ON

    def test_all_profiles_off(self, monkeypatch):
        monkeypatch.setattr(
            FirewallManager, "_read_registry_states",
            staticmethod(lambda: [False, False, False]),
        )
        assert FirewallManager().query_state() == STATE_OFF

    def test_mixed_profiles(self, monkeypatch):
        monkeypatch.setattr(
            FirewallManager, "_read_registry_states",
            staticmethod(lambda: [True, False, True]),
        )
        assert FirewallManager().query_state() == STATE_PARTIAL

    def test_unreadable_registry_is_unknown(self, monkeypatch):
        monkeypatch.setattr(
            FirewallManager, "_read_registry_states",
            staticmethod(lambda: None),
        )
        assert FirewallManager().query_state() == STATE_UNKNOWN


class TestNonAdminPath:
    def _no_admin(self, monkeypatch):
        monkeypatch.setattr(firewall, "is_admin", lambda: False)

    def test_disable_requests_elevation(self, monkeypatch):
        self._no_admin(monkeypatch)
        captured = {}

        def fake_elevate(lines, name_prefix="pingtool"):
            captured["lines"] = lines
            captured["prefix"] = name_prefix
            return True

        monkeypatch.setattr(firewall, "run_elevated_batch", fake_elevate)
        success, message, elevated = FirewallManager().disable()

        assert success is True
        assert elevated is True
        assert "管理员" in message
        assert "netsh advfirewall set allprofiles state off" in captured["lines"]
        assert captured["prefix"] == "firewall"

    def test_enable_requests_elevation(self, monkeypatch):
        self._no_admin(monkeypatch)
        captured = {}

        def fake_elevate(lines, name_prefix="pingtool"):
            captured["lines"] = lines
            return True

        monkeypatch.setattr(firewall, "run_elevated_batch", fake_elevate)
        success, _, elevated = FirewallManager().enable()

        assert success is True and elevated is True
        assert "netsh advfirewall set allprofiles state on" in captured["lines"]

    def test_elevation_refused(self, monkeypatch):
        self._no_admin(monkeypatch)
        monkeypatch.setattr(firewall, "run_elevated_batch", lambda *a, **k: False)
        success, message, elevated = FirewallManager().disable()

        assert success is False
        assert message == "需要管理员权限"
        assert elevated is False


class TestAdminPath:
    def _admin(self, monkeypatch):
        monkeypatch.setattr(firewall, "is_admin", lambda: True)

    def _run_result(self, returncode=0, stdout="", stderr=""):
        return subprocess.CompletedProcess(
            args=["netsh"], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_disable_success(self, monkeypatch):
        self._admin(monkeypatch)
        with mock.patch("ping_tool.core.firewall.subprocess.run",
                        return_value=self._run_result()) as run:
            success, message, elevated = FirewallManager().disable()

        assert success is True
        assert "已关闭" in message
        assert elevated is False
        args = run.call_args[0][0]
        assert args == ["netsh", "advfirewall", "set", "allprofiles", "state", "off"]

    def test_enable_success(self, monkeypatch):
        self._admin(monkeypatch)
        with mock.patch("ping_tool.core.firewall.subprocess.run",
                        return_value=self._run_result()) as run:
            success, message, _ = FirewallManager().enable()

        assert success is True
        assert "已开启" in message
        assert run.call_args[0][0][-1] == "on"

    def test_netsh_failure_reported(self, monkeypatch):
        self._admin(monkeypatch)
        with mock.patch(
            "ping_tool.core.firewall.subprocess.run",
            return_value=self._run_result(returncode=1, stderr="拒绝访问"),
        ):
            success, message, elevated = FirewallManager().disable()

        assert success is False
        assert elevated is False
        assert "拒绝访问" in message

    def test_timeout_reported(self, monkeypatch):
        self._admin(monkeypatch)
        with mock.patch(
            "ping_tool.core.firewall.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="netsh", timeout=1),
        ):
            success, message, _ = FirewallManager().disable()

        assert success is False
        assert "超时" in message

    def test_oserror_reported(self, monkeypatch):
        self._admin(monkeypatch)
        with mock.patch(
            "ping_tool.core.firewall.subprocess.run",
            side_effect=OSError("netsh 不存在"),
        ):
            success, message, _ = FirewallManager().disable()

        assert success is False
        assert "netsh 不存在" in message
