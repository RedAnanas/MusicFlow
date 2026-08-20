import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.watcher import watcher_service
from app.models import WatchFolder
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)


class WatchFolderManager:
    """统一管理监控目录、实时事件和周期扫描。"""

    WATCH_FOLDERS_FILE = "watch_folders.json"
    MAX_EVENTS_PER_FOLDER = 100

    def __init__(self):
        self.watch_folders: Dict[str, WatchFolder] = {}
        self.runtime_status: Dict[str, Dict[str, Any]] = {}
        self.event_history: Dict[str, List[Dict[str, Any]]] = {}
        self.next_scan_at: Dict[str, float] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.periodic_task: Optional[asyncio.Task] = None
        self.load_watch_folders()

    def load_watch_folders(self):
        """从本地配置加载监控目录。"""
        data = config_manager.load(self.WATCH_FOLDERS_FILE) or {}
        for folder_id, folder_data in data.items():
            try:
                folder = WatchFolder(**folder_data)
                self.watch_folders[folder_id] = folder
                self._ensure_runtime(folder_id)
            except Exception as exc:
                logger.error(f"Invalid watch folder {folder_id}: {exc}")

    def save_watch_folders(self):
        """持久化监控目录配置。"""
        data = {
            folder_id: folder.model_dump()
            for folder_id, folder in self.watch_folders.items()
        }
        if not config_manager.save(self.WATCH_FOLDERS_FILE, data):
            raise RuntimeError("Failed to save watch folder configuration")

    async def start(self):
        """在 FastAPI 事件循环中启动实时和周期监控。"""
        self.loop = asyncio.get_running_loop()
        for folder in self.watch_folders.values():
            if folder.enabled:
                self._start_watching(folder)
            self._schedule_next_scan(folder)

        if not self.periodic_task or self.periodic_task.done():
            self.periodic_task = asyncio.create_task(self._periodic_scan_loop())
        logger.info(f"Watch folder manager started ({len(self.watch_folders)} folders)")

    async def stop(self):
        """停止周期任务和全部实时监听。"""
        if self.periodic_task:
            self.periodic_task.cancel()
            try:
                await self.periodic_task
            except asyncio.CancelledError:
                pass
            self.periodic_task = None
        watcher_service.stop_all()
        self.loop = None
        logger.info("Watch folder manager stopped")

    def get_watch_folder(self, folder_id: str) -> Optional[WatchFolder]:
        return self.watch_folders.get(folder_id)

    def get_all_watch_folders(self) -> List[WatchFolder]:
        return list(self.watch_folders.values())

    def create_watch_folder(self, folder: WatchFolder) -> WatchFolder:
        self.watch_folders[folder.id] = folder
        self._ensure_runtime(folder.id)
        self.save_watch_folders()
        self._schedule_next_scan(folder)
        if folder.enabled:
            self._start_watching(folder)
            self._schedule_initial_scan(folder)
        self._record_event(folder.id, "configured", "监控目录已创建")
        logger.info(f"Created watch folder: {folder.name}")
        return folder

    def update_watch_folder(self, folder_id: str, folder: WatchFolder) -> Optional[WatchFolder]:
        old_folder = self.watch_folders.get(folder_id)
        if not old_folder:
            return None

        watcher_service.stop_watch(old_folder.input_dir)
        self.watch_folders[folder_id] = folder
        self.save_watch_folders()
        self._schedule_next_scan(folder)
        if folder.enabled:
            self._start_watching(folder)
        self._record_event(folder_id, "configured", "监控目录配置已更新")
        logger.info(f"Updated watch folder: {folder.name}")
        return folder

    def delete_watch_folder(self, folder_id: str) -> bool:
        folder = self.watch_folders.get(folder_id)
        if not folder:
            return False

        watcher_service.stop_watch(folder.input_dir)
        del self.watch_folders[folder_id]
        self.runtime_status.pop(folder_id, None)
        self.event_history.pop(folder_id, None)
        self.next_scan_at.pop(folder_id, None)
        self.save_watch_folders()
        logger.info(f"Deleted watch folder: {folder.name}")
        return True

    def toggle_watch_folder(self, folder_id: str) -> Optional[WatchFolder]:
        folder = self.watch_folders.get(folder_id)
        if not folder:
            return None

        folder.enabled = not folder.enabled
        if folder.enabled:
            self._start_watching(folder)
            self._schedule_next_scan(folder)
            self._schedule_initial_scan(folder)
        else:
            watcher_service.stop_watch(folder.input_dir)
        self.save_watch_folders()
        state = "启用" if folder.enabled else "停用"
        self._record_event(folder_id, "configured", f"监控已{state}")
        return folder

    def scan_watch_folder(self, folder_id: str) -> List[str]:
        folder = self.watch_folders.get(folder_id)
        if not folder:
            return []

        files = self._scan_directory(folder.input_dir, folder.recursive_scan)
        status = self._ensure_runtime(folder_id)
        status["last_scan"] = datetime.now().isoformat()
        status["last_scan_count"] = len(files)
        self._record_event(folder_id, "scan", f"扫描发现 {len(files)} 个音频文件")
        return files

    async def process_watch_folder(self, folder_id: str, trigger: str = "manual") -> Dict[str, Any]:
        folder = self.watch_folders.get(folder_id)
        if not folder:
            return {"files": [], "created_tasks": 0}

        files = self.scan_watch_folder(folder_id)
        created_tasks = 0
        for file_path in files:
            created_tasks += await self._process_file(folder, file_path, trigger)

        self._record_event(
            folder_id,
            "processed",
            f"{trigger} 扫描创建 {created_tasks} 个转换任务",
        )
        return {"files": files, "created_tasks": created_tasks}

    def get_status(self, folder_id: str) -> Dict[str, Any]:
        folder = self.watch_folders.get(folder_id)
        if not folder:
            return {}
        status = dict(self._ensure_runtime(folder_id))
        status["watching"] = folder.enabled and watcher_service.is_watching(folder.input_dir)
        status["enabled"] = folder.enabled
        status["next_scan_at"] = self._next_scan_iso(folder_id)
        return status

    def get_events(self, folder_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self.event_history.get(folder_id, [])[-limit:]))

    def _start_watching(self, folder: WatchFolder):
        if not self.loop:
            self._ensure_runtime(folder.id)["last_error"] = "服务尚未完成启动"
            return

        def on_file_found(file_path: str):
            if not self.loop or self.loop.is_closed():
                return
            future = asyncio.run_coroutine_threadsafe(
                self._handle_realtime_file(folder.id, file_path),
                self.loop,
            )
            future.add_done_callback(self._log_callback_error)

        started = watcher_service.start_watch(
            path=folder.input_dir,
            callback=on_file_found,
            supported_formats=set(settings.SUPPORTED_FORMATS),
            recursive=folder.recursive_scan,
        )
        status = self._ensure_runtime(folder.id)
        status["watching"] = started
        status["last_error"] = None if started else "实时监控启动失败，请检查目录和日志"
        if started:
            self._record_event(folder.id, "watching", "实时监控已启动")

    async def _handle_realtime_file(self, folder_id: str, file_path: str):
        folder = self.watch_folders.get(folder_id)
        if not folder or not folder.enabled:
            return

        self._record_event(folder_id, "detected", f"检测到稳定文件：{file_path}")
        if not folder.auto_process:
            self._record_event(folder_id, "ignored", "自动处理已关闭，仅记录文件事件")
            return
        created = await self._process_file(folder, file_path, "realtime")
        self._record_event(folder_id, "processed", f"实时事件创建 {created} 个转换任务")

    async def _process_file(self, folder: WatchFolder, file_path: str, trigger: str) -> int:
        from app.api.routes.tasks import TaskCreate, enqueue_conversion_task
        from app.services.profile_manager import profile_manager

        source_path = Path(file_path)
        created = 0
        for profile_id in folder.profile_ids:
            profile = profile_manager.get_profile(profile_id)
            if not profile or not profile.enabled:
                self._record_event(folder.id, "error", f"输出配置不可用：{profile_id}")
                continue

            output_file = self._build_output_path(folder, source_path, profile)
            task = await enqueue_conversion_task(
                TaskCreate(
                    source_file=str(source_path),
                    output_file=str(output_file),
                    profile_id=profile_id,
                ),
                skip_existing=True,
            )
            if task:
                created += 1
                self._record_event(
                    folder.id,
                    "task",
                    f"{trigger} 创建任务：{source_path.name} -> {output_file}",
                )

        status = self._ensure_runtime(folder.id)
        status["created_tasks"] = status.get("created_tasks", 0) + created
        return created

    def _build_output_path(self, folder: WatchFolder, source_path: Path, profile) -> Path:
        output_root = Path(folder.output_dir or profile.output_dir or settings.MUSIC_OUTPUT_DIR)
        try:
            relative_path = source_path.relative_to(Path(folder.input_dir))
        except ValueError:
            relative_path = Path(source_path.name)

        if len(folder.profile_ids) > 1:
            output_root = output_root / profile.id
        return output_root / relative_path.with_suffix(f".{profile.output_format.value}")

    async def _periodic_scan_loop(self):
        while True:
            try:
                now = time.monotonic()
                for folder in list(self.watch_folders.values()):
                    due_at = self.next_scan_at.get(folder.id, now)
                    if folder.enabled and folder.auto_process and now >= due_at:
                        try:
                            await self.process_watch_folder(folder.id, "periodic")
                            self._ensure_runtime(folder.id)["last_error"] = None
                        except Exception as exc:
                            self._ensure_runtime(folder.id)["last_error"] = str(exc)
                            self._record_event(folder.id, "error", f"周期扫描失败：{exc}")
                            logger.exception(f"Periodic scan failed for {folder.name}")
                        finally:
                            self._schedule_next_scan(folder)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(f"Watch folder periodic loop failed: {exc}")
                await asyncio.sleep(5)

    def _schedule_next_scan(self, folder: WatchFolder):
        interval_seconds = max(folder.scan_interval_minutes, 1) * 60
        self.next_scan_at[folder.id] = time.monotonic() + interval_seconds

    def _schedule_initial_scan(self, folder: WatchFolder):
        """在新增或重新启用目录后补偿处理已有文件。"""
        if not folder.auto_process or not self.loop or self.loop.is_closed():
            return

        async def process_existing_files():
            try:
                result = await self.process_watch_folder(folder.id, "initial")
                self._ensure_runtime(folder.id)["last_error"] = None
                self._record_event(
                    folder.id,
                    "initial",
                    f"初始扫描创建 {result['created_tasks']} 个转换任务",
                )
            except Exception as exc:
                self._ensure_runtime(folder.id)["last_error"] = str(exc)
                self._record_event(folder.id, "error", f"初始扫描失败：{exc}")
                logger.exception(f"Initial scan failed for {folder.name}")

        self.loop.create_task(process_existing_files())

    def _next_scan_iso(self, folder_id: str) -> Optional[str]:
        due_at = self.next_scan_at.get(folder_id)
        if due_at is None:
            return None
        seconds = max(due_at - time.monotonic(), 0)
        return datetime.fromtimestamp(time.time() + seconds).isoformat()

    def _scan_directory(self, directory: str, recursive: bool = True) -> List[str]:
        directory_path = Path(directory)
        if not directory_path.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        pattern = "**/*" if recursive else "*"
        supported = {ext.lower().lstrip(".") for ext in settings.SUPPORTED_FORMATS}
        files = [
            str(path)
            for path in directory_path.glob(pattern)
            if path.is_file() and path.suffix.lower().lstrip(".") in supported
        ]
        logger.info(f"Found {len(files)} files in {directory}")
        return files

    def _ensure_runtime(self, folder_id: str) -> Dict[str, Any]:
        return self.runtime_status.setdefault(
            folder_id,
            {
                "watching": False,
                "last_scan": None,
                "last_scan_count": 0,
                "last_event": None,
                "last_error": None,
                "created_tasks": 0,
            },
        )

    def _record_event(self, folder_id: str, event_type: str, message: str):
        timestamp = datetime.now().isoformat()
        events = self.event_history.setdefault(folder_id, [])
        events.append({"timestamp": timestamp, "type": event_type, "message": message})
        if len(events) > self.MAX_EVENTS_PER_FOLDER:
            del events[:-self.MAX_EVENTS_PER_FOLDER]
        self._ensure_runtime(folder_id)["last_event"] = timestamp
        logger.info(f"Watch folder {folder_id} [{event_type}]: {message}")

    @staticmethod
    def _log_callback_error(future):
        try:
            future.result()
        except Exception as exc:
            logger.exception(f"Realtime watch callback failed: {exc}")


watch_folder_manager = WatchFolderManager()
