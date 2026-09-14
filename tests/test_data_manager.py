"""DataManager 单元测试（使用临时目录，不触碰真实 targets.json）。"""
import json

import pytest

from ping_tool.data.manager import DataManager


@pytest.fixture
def manager(tmp_path):
    m = DataManager(tmp_path / "targets.json")
    # 隔离真实环境配置，避免外部 max_targets 干扰测试
    m._config._config["max_targets"] = 100
    return m


class TestLoad:
    def test_missing_file_returns_empty(self, manager):
        assert manager.load() == []

    def test_empty_list(self, manager, tmp_path):
        (tmp_path / "targets.json").write_text("[]", encoding="utf-8")
        assert manager.load() == []

    def test_corrupted_file_returns_empty(self, manager, tmp_path):
        (tmp_path / "targets.json").write_text("{oops", encoding="utf-8")
        assert manager.load() == []

    def test_non_list_returns_empty(self, manager, tmp_path):
        (tmp_path / "targets.json").write_text('{"a": 1}', encoding="utf-8")
        assert manager.load() == []

    def test_dedup_and_dirty_data(self, manager, tmp_path):
        # 历史脏数据：多余空白、大小写不一致、重复项、非字符串
        (tmp_path / "targets.json").write_text(
            json.dumps(["  BAIDU.COM ", "baidu.com", 42, "8.8.8.8"]),
            encoding="utf-8",
        )
        assert manager.load() == ["baidu.com", "8.8.8.8"]


class TestAdd:
    def test_add_valid(self, manager):
        ok, msg = manager.add("8.8.8.8")
        assert ok and msg == ""
        assert manager.load() == ["8.8.8.8"]

    def test_add_sanitizes(self, manager):
        ok, _ = manager.add("  BAIDU.COM  ")
        assert ok
        assert manager.load() == ["baidu.com"]

    def test_add_duplicate(self, manager):
        manager.add("baidu.com")
        ok, msg = manager.add("BAIDU.COM")
        assert not ok
        assert "已存在" in msg
        assert manager.load() == ["baidu.com"]

    def test_add_invalid(self, manager):
        ok, msg = manager.add("999.999.999.999")
        assert not ok
        assert manager.load() == []

    def test_add_empty(self, manager):
        ok, msg = manager.add("   ")
        assert not ok
        assert "空" in msg

    def test_add_reserved(self, manager):
        ok, msg = manager.add("127.0.0.1")
        assert not ok
        assert "保留" in msg

    def test_add_reaches_max(self, manager):
        # 默认 max_targets=20 依赖真实配置，可能不稳定；直接改实例配置
        manager._config._config["max_targets"] = 2
        manager.add("8.8.8.8")
        manager.add("9.9.9.9")
        ok, msg = manager.add("10.10.10.10")
        assert not ok
        assert "最多" in msg


class TestDelete:
    def test_delete_existing(self, manager):
        manager.add("baidu.com")
        ok, msg = manager.delete("BAIDU.COM")
        assert ok and msg == ""
        assert manager.load() == []

    def test_delete_missing(self, manager):
        ok, msg = manager.delete("nope.example")
        assert not ok
        assert "不存在" in msg


class TestSave:
    def test_save_atomic_and_no_tmp_leftover(self, manager, tmp_path):
        assert manager.save(["8.8.8.8", "baidu.com"]) is True
        assert (tmp_path / "targets.json").read_text(encoding="utf-8") is not None
        # 不应残留临时文件
        assert not (tmp_path / "targets.json.tmp").exists()
        assert json.loads((tmp_path / "targets.json").read_text(encoding="utf-8")) == [
            "8.8.8.8",
            "baidu.com",
        ]

    def test_save_preserves_unicode(self, manager):
        # save 直接写入，不经过校验：验证 ensure_ascii=False 生效
        assert manager.save(["中文目标"]) is True
        raw = manager._file_path.read_text(encoding="utf-8")
        assert "中文目标" in raw

    def test_save_roundtrip(self, manager):
        manager.add("8.8.8.8")
        assert manager.load() == ["8.8.8.8"]
