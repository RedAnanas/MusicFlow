import logging
import time
from pathlib import Path
from typing import Set, Dict, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

logger = logging.getLogger(__name__)


class FileStabilityChecker:
    """文件稳定性检查器 - 等待文件下载完成"""

    def __init__(self, stable_seconds: int = 30):
        self.stable_seconds = stable_seconds
        self.file_sizes: Dict[str, int] = {}
        self.last_checked: Dict[str, float] = {}

    def check_stability(self, file_path: str) -> bool:
        """
        检查文件是否稳定（大小不再变化）

        Returns:
            bool: 文件是否已稳定
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return False

            current_size = path.stat().st_size
            current_time = time.time()

            if file_path not in self.file_sizes:
                self.file_sizes[file_path] = current_size
                self.last_checked[file_path] = current_time
                return False

            last_size = self.file_sizes[file_path]
            last_time = self.last_checked[file_path]

            if current_size == last_size:
                elapsed = current_time - last_time
                if elapsed >= self.stable_seconds:
                    return True
            else:
                self.file_sizes[file_path] = current_size
                self.last_checked[file_path] = current_time

            return False

        except Exception as e:
            logger.error(f"Error checking file stability: {e}")
            return False


class MusicFileHandler(FileSystemEventHandler):
    """音乐文件监控处理器"""

    def __init__(
        self,
        callback: Callable[[str], None],
        supported_formats: Set[str],
        stability_checker: FileStabilityChecker
    ):
        self.callback = callback
        self.supported_formats = supported_formats
        self.stability_checker = stability_checker

    def on_created(self, event):
        if event.is_directory:
            return

        self._handle_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return

        self._handle_file(event.src_path)

    def _handle_file(self, file_path: str):
        """处理文件事件"""
        try:
            path = Path(file_path)

            if path.suffix.lower() not in self.supported_formats:
                return

            if not path.exists():
                return

            # 检查文件稳定性
            if not self.stability_checker.check_stability(file_path):
                logger.debug(f"File not stable yet: {file_path}")
                return

            logger.info(f"File stable, processing: {file_path}")
            self.callback(file_path)

        except Exception as e:
            logger.error(f"Error handling file {file_path}: {e}")


class WatcherService:
    """Watchdog 监控服务"""

    def __init__(self, stable_seconds: int = 30):
        self.observer = Observer()
        self.stability_checker = FileStabilityChecker(stable_seconds)
        self.watched_paths: Dict[str, bool] = {}

    def start_watch(
        self,
        path: str,
        callback: Callable[[str], None],
        supported_formats: Set[str],
        recursive: bool = True
    ):
        """开始监控目录"""
        try:
            watch_path = Path(path)
            if not watch_path.exists():
                logger.error(f"Watch path does not exist: {path}")
                return

            handler = MusicFileHandler(
                callback=callback,
                supported_formats=supported_formats,
                stability_checker=self.stability_checker
            )

            self.observer.schedule(handler, str(watch_path), recursive=recursive)
            self.watched_paths[path] = True
            logger.info(f"Started watching: {path}")

            if not self.observer.is_alive():
                self.observer.start()

        except Exception as e:
            logger.error(f"Error starting watcher for {path}: {e}")

    def stop_watch(self, path: str):
        """停止监控目录"""
        if path in self.watched_paths:
            del self.watched_paths[path]
            logger.info(f"Stopped watching: {path}")

    def stop_all(self):
        """停止所有监控"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.watched_paths.clear()
        logger.info("All watchers stopped")


watcher_service = WatcherService()
