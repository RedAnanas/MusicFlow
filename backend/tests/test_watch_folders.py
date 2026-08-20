from app.models import WatchFolder
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
