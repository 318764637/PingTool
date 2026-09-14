import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "PingTool"
APP_VERSION = "1.1.0"

DEFAULT_CONFIG = {
    "window_width": 500,
    "window_height": 640,
    "ping_interval": 1.0,
    "ping_timeout": 3000,
    "buffer_size": 4,
    "max_targets": 20,
    "log_max_bytes": 5 * 1024 * 1024,
    "log_backup_count": 3,
    "tailscale_stop_wait": 3,
    "tailscale_cmd_timeout": 30,
    "firewall_cmd_timeout": 30,
}

_TRUE_VALUES = {"1", "true", "yes", "on"}

_config_instance = None


class Config:
    def __init__(self):
        self._config = dict(DEFAULT_CONFIG)
        self._config_file = Path(os.environ.get("APPDATA", ".")) / APP_NAME / "config.json"
        self._load_from_file()
        self._load_from_env()

    @staticmethod
    def _coerce(key, value, current):
        """将外部来源（文件/环境变量）的原始值转换为配置项的目标类型。

        bool 按字符串语义解析（避免 bool("false") == True 的陷阱）；
        数值转换失败由调用方捕获，不在此抛异常。
        """
        if isinstance(current, bool):
            return str(value).strip().lower() in _TRUE_VALUES
        if current is not None:
            return type(current)(value)
        return value

    def _load_from_file(self):
        try:
            if self._config_file.exists():
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    logger.warning(f"配置文件格式错误，忽略: {self._config_file}")
                    return
                for key, value in data.items():
                    if key not in DEFAULT_CONFIG:
                        logger.warning(f"忽略未知配置项: {key}")
                        continue
                    try:
                        self._config[key] = self._coerce(key, value, self._config[key])
                    except (ValueError, TypeError):
                        logger.warning(f"配置项 {key} 类型无效，使用默认值")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取配置文件失败: {e}")

    def _load_from_env(self):
        prefix = "PINGTOOL_"
        for key in self._config:
            env_key = prefix + key.upper()
            env_val = os.environ.get(env_key)
            if env_val is None:
                continue
            try:
                self._config[key] = self._coerce(key, env_val, self._config[key])
            except (ValueError, TypeError):
                logger.warning(f"环境变量 {env_key} 解析失败，使用默认值")

    def get(self, key, default=None):
        return self._config.get(key, default)

    def __getitem__(self, key):
        return self._config[key]

    def save(self):
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except OSError as e:
            logger.error(f"保存配置文件失败: {e}")
            return False


def get_config():
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
