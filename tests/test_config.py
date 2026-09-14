"""config 模块单元测试。

注意：Config 单例（get_config）会读取真实环境；测试统一直接实例化
Config，并通过 monkeypatch 隔离 APPDATA 与 PINGTOOL_* 环境变量。
"""
import json
import os

import pytest

from ping_tool.config import Config, DEFAULT_CONFIG, _TRUE_VALUES


def _clean_env(monkeypatch):
    """清理可能干扰测试的 PINGTOOL_* 变量并重定向 APPDATA。"""
    for key in list(os.environ):
        if key.startswith("PINGTOOL_"):
            monkeypatch.delenv(key, raising=False)


def make_config(monkeypatch, tmp_path, env_overrides=None):
    _clean_env(monkeypatch)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    if env_overrides:
        for key, value in env_overrides.items():
            monkeypatch.setenv(key, value)
    return Config()


class TestCoerce:
    def test_bool_semantics(self):
        assert Config._coerce("k", "true", True) is True
        assert Config._coerce("k", "TRUE", True) is True
        assert Config._coerce("k", "1", True) is True
        assert Config._coerce("k", "yes", True) is True
        assert Config._coerce("k", "on", True) is True
        # 经典陷阱：bool("false") == True
        assert Config._coerce("k", "false", True) is False
        assert Config._coerce("k", "0", True) is False
        assert Config._coerce("k", "no", True) is False

    def test_int(self):
        assert Config._coerce("k", "42", 0) == 42

    def test_float(self):
        assert Config._coerce("k", "1.5", 0.0) == 1.5

    def test_str(self):
        assert Config._coerce("k", "hello", "default") == "hello"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            Config._coerce("k", "abc", 0)


class TestConfigFromEnv:
    def test_int_env(self, monkeypatch, tmp_path):
        cfg = make_config(monkeypatch, tmp_path, {"PINGTOOL_MAX_TARGETS": "7"})
        assert cfg.get("max_targets") == 7

    def test_float_env(self, monkeypatch, tmp_path):
        cfg = make_config(monkeypatch, tmp_path, {"PINGTOOL_PING_INTERVAL": "0.5"})
        assert cfg.get("ping_interval") == 0.5

    def test_bool_env(self, monkeypatch, tmp_path):
        # 当前无 bool 配置项；验证 _coerce 语义即可
        assert _TRUE_VALUES == {"1", "true", "yes", "on"}

    def test_invalid_env_keeps_default(self, monkeypatch, tmp_path):
        cfg = make_config(monkeypatch, tmp_path, {"PINGTOOL_PING_INTERVAL": "abc"})
        assert cfg.get("ping_interval") == DEFAULT_CONFIG["ping_interval"]

    def test_defaults(self, monkeypatch, tmp_path):
        cfg = make_config(monkeypatch, tmp_path)
        assert cfg.get("max_targets") == 20
        assert cfg.get("ping_timeout") == 3000


class TestConfigFromFile:
    def test_load_valid_file(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"max_targets": 5, "window_width": 600}), encoding="utf-8"
        )
        cfg = make_config(monkeypatch, tmp_path)
        assert cfg.get("max_targets") == 5
        assert cfg.get("window_width") == 600
        # 未写入的项保持默认
        assert cfg.get("ping_timeout") == 3000

    def test_unknown_key_ignored(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"bogus_key": 123}), encoding="utf-8"
        )
        cfg = make_config(monkeypatch, tmp_path)
        assert "bogus_key" not in cfg._config

    def test_bad_type_falls_back_to_default(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"max_targets": "not-a-number"}), encoding="utf-8"
        )
        cfg = make_config(monkeypatch, tmp_path)
        assert cfg.get("max_targets") == DEFAULT_CONFIG["max_targets"]

    def test_corrupted_file_does_not_crash(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text("{broken json", encoding="utf-8")
        cfg = make_config(monkeypatch, tmp_path)
        assert cfg.get("max_targets") == DEFAULT_CONFIG["max_targets"]

    def test_non_dict_file_ignored(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text("[1, 2, 3]", encoding="utf-8")
        cfg = make_config(monkeypatch, tmp_path)
        assert cfg.get("max_targets") == DEFAULT_CONFIG["max_targets"]

    def test_env_overrides_file(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / "PingTool"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"max_targets": 5}), encoding="utf-8"
        )
        cfg = make_config(
            monkeypatch, tmp_path, {"PINGTOOL_MAX_TARGETS": "9"}
        )
        assert cfg.get("max_targets") == 9


class TestConfigSave:
    def test_save_roundtrip(self, monkeypatch, tmp_path):
        cfg = make_config(monkeypatch, tmp_path)
        cfg._config["max_targets"] = 12
        assert cfg.save() is True
        saved = json.loads((tmp_path / "PingTool" / "config.json").read_text(encoding="utf-8"))
        assert saved["max_targets"] == 12
