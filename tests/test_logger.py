"""logger 模块单元测试。"""
import logging

import pytest

import ping_tool.logger as pl


@pytest.fixture
def fresh_logger():
    """重置 logger 模块配置状态，测试结束后恢复。"""
    root = logging.getLogger()
    saved = {
        "handlers": list(root.handlers),
        "level": root.level,
        "configured": pl._configured,
    }
    root.handlers = []
    root.setLevel(logging.WARNING)
    pl._configured = False
    yield
    root.handlers = saved["handlers"]
    root.setLevel(saved["level"])
    pl._configured = saved["configured"]


def _flush_root():
    for handler in logging.getLogger().handlers:
        handler.flush()


class TestSetupLogger:
    def test_writes_to_file_and_console_child_logger(self, fresh_logger, tmp_path):
        log_file = tmp_path / "test.log"
        pl.setup_logger("app", log_file)

        # 子 logger（各模块实际使用 get_logger(__name__)）应能沿 propagate 输出
        child = logging.getLogger("ping_tool.core.ping_worker")
        child.info("child info message")
        child.debug("child debug message")
        _flush_root()

        content = log_file.read_text(encoding="utf-8")
        assert "child info message" in content
        assert "child debug message" in content

    def test_idempotent_second_call_no_extra_handlers(self, fresh_logger, tmp_path):
        lf1 = tmp_path / "a.log"
        lf2 = tmp_path / "b.log"
        pl.setup_logger("app1", lf1)
        handler_count = len(logging.getLogger().handlers)
        pl.setup_logger("app2", lf2)
        assert len(logging.getLogger().handlers) == handler_count
        assert not lf2.exists()

    def test_third_party_root_handler_does_not_skip_config(self, fresh_logger, tmp_path):
        """第三方库先挂 handler 不应导致本应用跳过日志配置。"""
        root = logging.getLogger()
        root.addHandler(logging.NullHandler())

        log_file = tmp_path / "test.log"
        pl.setup_logger("app", log_file)
        child = logging.getLogger("ping_tool.config")
        child.info("configured message")
        _flush_root()

        assert "configured message" in log_file.read_text(encoding="utf-8")

    def test_get_logger_returns_named_logger(self, fresh_logger):
        assert pl.get_logger("x.y") is logging.getLogger("x.y")
