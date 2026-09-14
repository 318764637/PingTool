import json
import os
import sys
from pathlib import Path

from ..config import get_config
from ..logger import get_logger
from ..utils.validators import sanitize_target, validate_target

logger = get_logger(__name__)


class DataManager:
    """管理 targets.json 的读写，提供增删查接口。"""

    def __init__(self, file_path=None):
        if file_path is None:
            file_path = self._get_project_root() / "targets.json"
        self._file_path = Path(file_path)
        self._config = get_config()

    @staticmethod
    def _get_project_root():
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        return Path(__file__).resolve().parent.parent.parent

    def load(self):
        try:
            if not self._file_path.exists():
                return []
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            # 过滤非字符串；对历史脏数据（多余空白/大小写不一致）做 sanitize
            # 并去重，保证与 add/delete 的持久化口径一致
            seen = set()
            result = []
            for item in data:
                if not isinstance(item, str):
                    continue
                clean = sanitize_target(item)
                if not clean or clean in seen:
                    continue
                seen.add(clean)
                result.append(clean)
            return result
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载目标文件失败: {e}")
            return []

    def save(self, targets):
        tmp_path = None
        try:
            # 先写临时文件再原子替换，避免进程中断损坏 targets.json
            tmp_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(targets, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._file_path)
            return True
        except OSError as e:
            logger.error(f"保存目标文件失败: {e}")
            return False
        finally:
            # 异常时清理残留的临时文件
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def add(self, target):
        target = sanitize_target(target)
        if not target:
            return False, "目标不能为空"
        valid, msg = validate_target(target)
        if not valid:
            return False, msg
        targets = self.load()
        max_targets = self._config.get("max_targets", 20)
        if len(targets) >= max_targets:
            return False, f"最多添加 {max_targets} 个目标"
        if target in targets:
            return False, "目标已存在"
        targets.append(target)
        if self.save(targets):
            return True, ""
        return False, "保存失败"

    def delete(self, target):
        target = sanitize_target(target)
        targets = self.load()
        if target not in targets:
            return False, "目标不存在"
        targets.remove(target)
        if self.save(targets):
            return True, ""
        return False, "保存失败"
