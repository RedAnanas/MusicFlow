import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional
from app.models import WatchFolder
from app.services.config_manager import config_manager
from app.core.watcher import watcher_service
from app.core import ffprobe_service, metadata_service

logger = logging.getLogger(__name__)


class WatchFolderManager:
    """监控目录管理器"""

    WATCH_FOLDERS_FILE = "watch_folders.json"

    def __init__(self):
        self.watch_folders: Dict[str, WatchFolder] = {}
        self.load_watch_folders()

    def load_watch_folders(self):
        """加载监控目录"""
        data = config_manager.load(self.WATCH_FOLDERS_FILE)
        if data:
            for folder_id, folder_dict in data.items():
                self.watch_folders[folder_id] = WatchFolder(**folder_dict)

    def save_watch_folders(self):
        """保存监控目录"""
        data = {folder_id: folder.dict() for folder_id, folder in self.watch_folders.items()}
        config_manager.save(self.WATCH_FOLDERS_FILE, data)

    def get_watch_folder(self, folder_id: str) -> Optional[WatchFolder]:
        """获取监控目录"""
        return self.watch_folders.get(folder_id)

    def get_all_watch_folders(self) -> List[WatchFolder]:
        """获取所有监控目录"""
        return list(self.watch_folders.values())

    def create_watch_folder(self, folder: WatchFolder) -> WatchFolder:
        """创建监控目录"""
        self.watch_folders[folder.id] = folder
        self.save_watch_folders()

        # 如果启用，开始监控
        if folder.enabled:
            self._start_watching(folder)

        logger.info(f"Created watch folder: {folder.name}")
        return folder

    def update_watch_folder(self, folder_id: str, folder: WatchFolder) -> Optional[WatchFolder]:
        """更新监控目录"""
        if folder_id in self.watch_folders:
            old_folder = self.watch_folders[folder_id]

            # 停止旧的监控
            if old_folder.enabled:
                watcher_service.stop_watch(old_folder.input_dir)

            self.watch_folders[folder_id] = folder
            self.save_watch_folders()

            # 如果启用，开始新的监控
            if folder.enabled:
                self._start_watching(folder)

            logger.info(f"Updated watch folder: {folder.name}")
            return folder
        return None

    def delete_watch_folder(self, folder_id: str) -> bool:
        """删除监控目录"""
        if folder_id in self.watch_folders:
            folder = self.watch_folders[folder_id]

            # 停止监控
            if folder.enabled:
                watcher_service.stop_watch(folder.input_dir)

            del self.watch_folders[folder_id]
            self.save_watch_folders()

            logger.info(f"Deleted watch folder: {folder.name}")
            return True
        return False

    def scan_watch_folder(self, folder_id: str) -> List[str]:
        """扫描监控目录"""
        if folder_id not in self.watch_folders:
            return []

        folder = self.watch_folders[folder_id]
        return self._scan_directory(folder.input_dir, folder.recursive_scan)

    def _start_watching(self, folder: WatchFolder):
        """开始监控目录"""
        try:
            from app.config import settings

            def on_file_found(file_path: str):
                # 这里应该触发转换流程
                logger.info(f"File found: {file_path}")

            watcher_service.start_watch(
                path=folder.input_dir,
                callback=on_file_found,
                supported_formats=set(settings.SUPPORTED_FORMATS),
                recursive=folder.recursive_scan
            )

        except Exception as e:
            logger.error(f"Error starting watcher for {folder.name}: {e}")

    def _scan_directory(self, directory: str, recursive: bool = True) -> List[str]:
        """扫描目录中的音乐文件"""
        from app.config import settings

        found_files = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.error(f"Directory does not exist: {directory}")
            return found_files

        pattern = "**/*" if recursive else "*"

        for file_path in dir_path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower()[1:] in settings.SUPPORTED_FORMATS:
                found_files.append(str(file_path))

        logger.info(f"Found {len(found_files)} files in {directory}")
        return found_files


watch_folder_manager = WatchFolderManager()
