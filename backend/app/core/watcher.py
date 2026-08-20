import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Set
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

logger = logging.getLogger(__name__)


class MusicFileHandler(FileSystemEventHandler):
    """音乐文件监控处理器"""

    def __init__(
        self,
        callback: Callable[[str], None],
        supported_formats: Set[str],
        stable_seconds: int,
    ):
        self.callback = callback
        self.supported_formats = {ext.lower().lstrip(".") for ext in supported_formats}
        self.stable_seconds = stable_seconds
        self.pending: Dict[str, threading.Timer] = {}
        self.signatures: Dict[str, tuple[int, int]] = {}
        self.lock = threading.Lock()

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

            if path.suffix.lower().lstrip(".") not in self.supported_formats:
                return

            if not path.exists():
                return

            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            with self.lock:
                existing_timer = self.pending.pop(file_path, None)
                if existing_timer:
                    existing_timer.cancel()
                self.signatures[file_path] = signature
                timer = threading.Timer(
                    self.stable_seconds,
                    self._process_if_stable,
                    args=(file_path, signature),
                )
                timer.daemon = True
                self.pending[file_path] = timer
                timer.start()
            logger.debug(f"Waiting for file stability: {file_path}")

        except Exception as exc:
            logger.error(f"Error handling file {file_path}: {exc}")

    def _process_if_stable(self, file_path: str, expected: tuple[int, int]):
        """稳定时间到期后再次核对文件，避免处理未写完的下载。"""
        try:
            path = Path(file_path)
            if not path.exists():
                return
            stat = path.stat()
            current = (stat.st_size, stat.st_mtime_ns)
            if current != expected:
                self._handle_file(file_path)
                return

            with self.lock:
                if self.signatures.get(file_path) != expected:
                    return
                self.pending.pop(file_path, None)
                self.signatures.pop(file_path, None)

            logger.info(f"File stable, processing: {file_path}")
            self.callback(file_path)
        except Exception as exc:
            logger.error(f"Error processing stable file {file_path}: {exc}")

    def stop(self):
        """取消该目录中尚未到期的稳定性检查。"""
        with self.lock:
            for timer in self.pending.values():
                timer.cancel()
            self.pending.clear()
            self.signatures.clear()


class WatcherService:
    """Watchdog 监控服务"""

    def __init__(self, stable_seconds: int = 30):
        # WSL 访问 /mnt/d 时无法稳定接收 Windows 文件事件，使用轮询保证新增文件可被发现。
        self.observer = PollingObserver(timeout=1)
        self.stable_seconds = stable_seconds
        self.watched_paths: Dict[str, tuple[object, MusicFileHandler]] = {}

    def start_watch(
        self,
        path: str,
        callback: Callable[[str], None],
        supported_formats: Set[str],
        recursive: bool = True
    ) -> bool:
        """开始监控目录"""
        try:
            watch_path = Path(path)
            if not watch_path.exists():
                logger.error(f"Watch path does not exist: {path}")
                return False

            normalized_path = str(watch_path.resolve())
            self.stop_watch(normalized_path)

            handler = MusicFileHandler(
                callback=callback,
                supported_formats=supported_formats,
                stable_seconds=self.stable_seconds,
            )

            watch = self.observer.schedule(handler, normalized_path, recursive=recursive)
            self.watched_paths[normalized_path] = (watch, handler)
            logger.info(f"Started watching: {normalized_path}")

            if not self.observer.is_alive():
                self.observer.start()
            return True

        except Exception as exc:
            logger.error(f"Error starting watcher for {path}: {exc}")
            return False

    def stop_watch(self, path: str):
        """停止监控目录"""
        normalized_path = str(Path(path).resolve())
        watcher = self.watched_paths.pop(normalized_path, None)
        if watcher:
            watch, handler = watcher
            handler.stop()
            self.observer.unschedule(watch)
            logger.info(f"Stopped watching: {normalized_path}")

    def is_watching(self, path: str) -> bool:
        """返回目录是否已注册实时监控。"""
        return str(Path(path).resolve()) in self.watched_paths

    def stop_all(self):
        """停止所有监控"""
        for _, handler in self.watched_paths.values():
            handler.stop()
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.watched_paths.clear()
        logger.info("All watchers stopped")


watcher_service = WatcherService()
