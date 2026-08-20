import asyncio

from app.models import WatchFolder
from app.core import watcher
from app.services.watch_folder_manager import WatchFolderManager, watcher_service


def test_disabled_folder_is_not_reported_as_watching(monkeypatch):
    """停用目录即使与其他监听共用路径，也不应显示为监听中。"""
    manager = WatchFolderManager()
    folder = WatchFolder(
        id="disabled-folder",
        name="停用目录",
        input_dir="/shared/music",
        profile_ids=[],
        enabled=False,
    )
    manager.watch_folders = {folder.id: folder}

    monkeypatch.setattr(watcher_service, "is_watching", lambda _path: True)

    status = manager.get_status(folder.id)

    assert status["enabled"] is False
    assert status["watching"] is False


def test_creating_enabled_folder_processes_existing_files(monkeypatch):
    """新增启用的目录应立即补偿处理已存在的音频文件。"""
    manager = WatchFolderManager()
    manager.watch_folders = {}
    processed = []

    async def process_watch_folder(folder_id, trigger):
        processed.append((folder_id, trigger))
        return {"files": ["/music/existing.flac"], "created_tasks": 1}

    async def create_folder():
        manager.loop = asyncio.get_running_loop()
        monkeypatch.setattr(manager, "save_watch_folders", lambda: None)
        monkeypatch.setattr(manager, "_start_watching", lambda _folder: None)
        monkeypatch.setattr(manager, "process_watch_folder", process_watch_folder)
        folder = WatchFolder(
            id="new-folder",
            name="新目录",
            input_dir="/music",
            profile_ids=["aac"],
            enabled=True,
            auto_process=True,
        )

        manager.create_watch_folder(folder)
        await asyncio.sleep(0)

    asyncio.run(create_folder())

    assert processed == [("new-folder", "initial")]


def test_watcher_uses_polling_observer(monkeypatch):
    """WSL 挂载的 Windows 目录应使用轮询监听。"""
    created_with = []

    class FakePollingObserver:
        def __init__(self, timeout):
            created_with.append(timeout)

    monkeypatch.setattr(watcher, "PollingObserver", FakePollingObserver)

    watcher.WatcherService()

    assert created_with == [1]
