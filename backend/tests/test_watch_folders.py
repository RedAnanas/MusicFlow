import asyncio
import time

from app.models import DeliveryTarget, DeliveryTargetType, WatchFolder
from app.api.routes.watch_folders import normalize_targets
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


def test_watcher_uses_native_observer(monkeypatch):
    """Windows 本地目录应使用原生文件事件监听。"""
    created = []

    class FakeObserver:
        def __init__(self):
            created.append(True)

    monkeypatch.setattr(watcher, "Observer", FakeObserver)

    watcher.WatcherService()

    assert created == [True]


def test_watcher_handles_atomic_move_into_folder(monkeypatch, tmp_path):
    """下载临时文件原子改名后应按最终音频路径触发处理。"""
    detected = []
    audio_file = tmp_path / "song.flac"
    audio_file.write_bytes(b"audio")
    handler = watcher.MusicFileHandler(detected.append, {"flac"}, stable_seconds=30)
    monkeypatch.setattr(handler, "_handle_file", detected.append)
    event = type("MovedEvent", (), {"is_directory": False, "dest_path": str(audio_file)})()

    handler.on_moved(event)

    assert detected == [str(audio_file)]


def test_watcher_ignores_musicdl_metadata_temp_file(tmp_path):
    """标签写入的随机后缀音频不应进入实时监控队列。"""
    detected = []
    temp_file = tmp_path / "song.8k2jxea3.flac"
    temp_file.write_bytes(b"audio")
    handler = watcher.MusicFileHandler(detected.append, {"flac"}, stable_seconds=30)

    handler._handle_file(str(temp_file))

    assert handler.pending == {}
    assert detected == []


def test_scan_skips_musicdl_temp_and_recent_audio(monkeypatch, tmp_path):
    """扫描只返回稳定的正式音频，下载和标签写入期间暂缓处理。"""
    manager = WatchFolderManager()
    audio_file = tmp_path / "song.flac"
    temp_file = tmp_path / "song.8k2jxea3.flac"
    audio_file.write_bytes(b"audio")
    temp_file.write_bytes(b"audio")
    created_at = time.time()

    assert manager._scan_directory(str(tmp_path)) == []

    monkeypatch.setattr("app.services.watch_folder_manager.time.time", lambda: created_at + 31)

    assert manager._scan_directory(str(tmp_path)) == [str(audio_file)]


def test_copy_target_preserves_relative_path_and_skips_existing(tmp_path):
    """飞牛音乐目标应原样复制，并避免覆盖已有文件。"""
    source_root = tmp_path / "source"
    source_file = source_root / "artist" / "album" / "song.flac"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"lossless music")
    output_root = tmp_path / "feiniu"
    folder = WatchFolder(
        id="copy-folder",
        name="飞牛音乐",
        input_dir=str(source_root),
        targets=[DeliveryTarget(type=DeliveryTargetType.COPY, output_dir=str(output_root))],
    )

    output_file = WatchFolderManager()._build_output_path(folder, source_file, folder.targets[0])

    assert WatchFolderManager._copy_file(source_file, output_file) is True
    assert output_file.read_bytes() == b"lossless music"
    assert WatchFolderManager._copy_file(source_file, output_file) is False


def test_copy_target_updates_media_presence_after_output(monkeypatch, tmp_path):
    """飞牛成品复制成功后增量更新资料库索引和补齐任务。"""
    from app.api.routes import discovery
    from app.services.acquisition_service import acquisition_service
    from app.services.media_library_service import media_library_service

    source_root = tmp_path / "downloads"
    source_root.mkdir()
    source_file = source_root / "song.flac"
    source_file.write_bytes(b"audio")
    output_root = tmp_path / "library"
    folder = WatchFolder(
        id="copy-folder",
        name="飞牛音乐",
        input_dir=str(source_root),
        targets=[DeliveryTarget(type=DeliveryTargetType.COPY, output_dir=str(output_root))],
    )
    indexed = []
    delivered = []
    invalidated = []
    monkeypatch.setattr(media_library_service, "index_output", lambda path: indexed.append(path) or True)
    monkeypatch.setattr(acquisition_service, "mark_nas_delivered", lambda source, output: delivered.append((source, output)))
    monkeypatch.setattr(discovery, "invalidate_presence_index", lambda: invalidated.append(True))

    asyncio.run(WatchFolderManager()._process_file(folder, str(source_file), "test"))

    assert indexed == [output_root / "song.flac"]
    assert delivered == [(str(source_file), output_root / "song.flac")]
    assert invalidated == [True]


def test_legacy_profile_configuration_is_migrated_to_convert_target():
    """已有监控目录应继续作为 Apple Music 转换目标运行。"""
    folder = WatchFolder(
        id="legacy-folder",
        name="旧配置",
        input_dir="/music/source",
        profile_ids=["aac"],
        output_dir="/music/output",
    )

    WatchFolderManager._migrate_legacy_targets(folder)

    assert folder.targets == [
        DeliveryTarget(
            type=DeliveryTargetType.CONVERT,
            profile_id="aac",
            output_dir="/music/output",
        )
    ]


def test_normalize_targets_accepts_model_dump_data():
    """更新已有目录时，序列化后的规则也必须能重新校验。"""
    target = DeliveryTarget(
        type=DeliveryTargetType.CONVERT,
        profile_id="aac",
        output_dir="/music/output",
    )

    normalized = normalize_targets({"targets": [target.model_dump()]})

    assert normalized == [target]
