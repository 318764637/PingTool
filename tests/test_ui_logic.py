"""UI 层纯逻辑测试（不启动 Tk 窗口）。

覆盖两处只在真实使用中才暴露的问题：
1. 目标卡片的网格行号分配（删除中间目标后再添加不得重叠）；
2. 后台线程结果经队列回主线程的分发逻辑（Tailscale / 防火墙）。

未安装 customtkinter 时注入轻量桩，以便在无 GUI 依赖的环境下也能跑这些逻辑。
"""
import queue
import sys
import types

import pytest

try:  # 已安装则用真实库，避免掩盖真实导入问题
    import customtkinter  # noqa: F401
except ImportError:
    def _make_ctk_stub():
        module = types.ModuleType("customtkinter")

        class _Widget:
            def __init__(self, *args, **kwargs):
                pass

            def __getattr__(self, name):
                def _noop(*args, **kwargs):
                    return None

                return _noop

        for name in (
            "CTk", "CTkFrame", "CTkButton", "CTkEntry",
            "CTkLabel", "CTkScrollableFrame", "CTkComboBox",
        ):
            setattr(module, name, type(name, (_Widget,), {}))
        module.set_appearance_mode = lambda *a, **k: None
        module.set_default_color_theme = lambda *a, **k: None
        return module

    sys.modules.setdefault("customtkinter", _make_ctk_stub())

import ping_tool.ui.app as app_module
from ping_tool.ui.app import PingApp


class FakeCard:
    """记录 grid 行号的卡片替身。"""

    def __init__(self, master, target, on_delete=None, **kwargs):
        self.target = target
        self.row = None

    def grid(self, **kwargs):
        self.row = kwargs.get("row")


class FakeFirewallCard:
    def __init__(self):
        self.busy = []
        self.states = []

    def set_busy(self, busy, action=None):
        self.busy.append(busy)

    def update_state(self, state, detail=""):
        self.states.append((state, detail))


class FakeTailscaleCard:
    def __init__(self):
        self.states = []

    def update_status(self, success, message):
        self.states.append((success, message))


class FakeStatusBar:
    def __init__(self):
        self.calls = []

    def set_status(self, text, color=None):
        self.calls.append((text, color))


def make_bare_app():
    """构造一个不执行 Tk 初始化的 PingApp，只保留被测逻辑所需状态。"""
    app = PingApp.__new__(PingApp)
    app._cards = {}
    app._next_row = 0
    app._scroll_frame = None
    return app


def add_card(app, target):
    PingApp._add_card(app, target)
    return app._cards[target]


@pytest.fixture
def fake_target_card(monkeypatch):
    monkeypatch.setattr(app_module, "TargetCard", FakeCard)


class TestTargetCardRows:
    def test_rows_are_sequential(self, fake_target_card):
        app = make_bare_app()
        assert [add_card(app, t).row for t in ("a.com", "b.com", "c.com")] == [0, 1, 2]

    def test_new_card_does_not_overlap_after_delete(self, fake_target_card):
        """删除中间目标后再添加：行号必须与仍在显示的卡片不同（修复前会重叠）。"""
        app = make_bare_app()
        for target in ("a.com", "b.com", "c.com"):
            add_card(app, target)

        # 与 _delete_target 相同的关键状态变更：卡片销毁 + 从字典移除
        del app._cards["b.com"]

        new_card = add_card(app, "d.com")
        rows = {target: card.row for target, card in app._cards.items()}

        assert new_card.row not in (app._cards["a.com"].row, app._cards["c.com"].row)
        assert len(set(rows.values())) == len(rows), f"行号冲突: {rows}"
        assert new_card.row == 3  # 只增不减

    def test_duplicate_target_not_added_twice(self, fake_target_card):
        app = make_bare_app()
        add_card(app, "a.com")
        add_card(app, "a.com")
        assert len(app._cards) == 1


class TestControlMessageDispatch:
    def _app_with_fakes(self):
        app = make_bare_app()
        app._control_queue = queue.Queue()
        app._firewall_card = FakeFirewallCard()
        app._tailscale_card = FakeTailscaleCard()
        app._status_bar = FakeStatusBar()
        return app

    def test_firewall_result_updates_card_and_status(self):
        app = self._app_with_fakes()
        app._control_queue.put((
            "firewall",
            {"success": True, "message": "防火墙已关闭", "state": "off", "detail": ""},
        ))

        PingApp._apply_control_messages(app)

        assert app._firewall_card.busy == [False]
        assert app._firewall_card.states == [("off", "")]
        assert app._status_bar.calls[-1][0] == "防火墙已关闭"
        assert app._control_queue.empty()

    def test_firewall_failure_keeps_detail(self):
        app = self._app_with_fakes()
        app._control_queue.put((
            "firewall",
            {
                "success": False,
                "message": "需要管理员权限",
                "state": "on",
                "detail": "需要管理员权限",
            },
        ))

        PingApp._apply_control_messages(app)

        assert app._firewall_card.states == [("on", "需要管理员权限")]
        assert app._status_bar.calls[-1][0] == "需要管理员权限"

    def test_tailscale_result_updates_card(self):
        app = self._app_with_fakes()
        app._control_queue.put(("tailscale", {"success": True, "message": "服务重启成功"}))

        PingApp._apply_control_messages(app)

        assert app._tailscale_card.states == [(True, "服务重启成功")]
        assert app._status_bar.calls[-1][0] == "Tailscale 重启成功"
