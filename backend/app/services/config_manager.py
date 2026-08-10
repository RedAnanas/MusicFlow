import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from app.config import settings

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 管理 JSON 配置文件"""

    def __init__(self):
        self.config_dir = Path(settings.CONFIG_DIR)

    def _get_file_path(self, filename: str) -> Path:
        """获取配置文件路径"""
        return self.config_dir / filename

    def load(self, filename: str) -> Optional[Dict]:
        """
        加载配置文件

        Args:
            filename: 文件名，如 'settings.json'

        Returns:
            Dict: 配置字典，如果加载失败返回 None
        """
        try:
            file_path = self._get_file_path(filename)
            if not file_path.exists():
                logger.warning(f"Config file not found: {file_path}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            self._backup_corrupted(filename)
            return None
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return None

    def save(self, filename: str, data: Dict) -> bool:
        """
        保存配置文件

        Args:
            filename: 文件名
            data: 要保存的数据

        Returns:
            bool: 是否成功
        """
        try:
            file_path = self._get_file_path(filename)

            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入临时文件，然后重命名（原子操作）
            temp_path = file_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            temp_path.replace(file_path)

            logger.info(f"Saved config: {filename}")
            return True

        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
            return False

    def _backup_corrupted(self, filename: str):
        """备份损坏的配置文件"""
        try:
            file_path = self._get_file_path(filename)
            if file_path.exists():
                backup_path = file_path.with_suffix('.json.bak')
                file_path.rename(backup_path)
                logger.info(f"Backed up corrupted config to {backup_path}")
        except Exception as e:
            logger.error(f"Error backing up corrupted config: {e}")


config_manager = ConfigManager()
