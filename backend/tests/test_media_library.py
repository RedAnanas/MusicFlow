import threading
from pathlib import Path

from app.services.file_index_service import FileIndexService
from app.services.media_library_service import MediaLibraryService
from app.services.config_manager import config_manager


def test_media_library_scan_deduplicates_tracks_across_sources(monkeypatch, tmp_path: Path) -> None:
    """多个整理媒体库包含相同曲目时，对账只保留一条本地候选。"""
    first = tmp_path / "first.flac"
    second = tmp_path / "second.flac"
    first.write_bytes(b"audio")
    second.write_bytes(b"audio")
    first_source = tmp_path / "one"
    second_source = tmp_path / "two"
    first_source.mkdir()
    second_source.mkdir()
    first.rename(first_source / first.name)
    second.rename(second_source / second.name)
    first = first_source / first.name
    second = second_source / second.name
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))
    monkeypatch.setattr(service, "get_sources", lambda: [str(first_source), str(second_source)])
    monkeypatch.setattr(service, "_read_track", lambda path: {
        "id": path.stem,
        "path": str(path),
        "filename": path.name,
        "title": "重复歌曲",
        "artist": "歌手",
        "album": "专辑",
        "isrc": "CNABC1234567",
    })

    tracks = service.load_tracks(refresh=True)

    assert [track["id"] for track in tracks] == ["first"]


def test_index_output_updates_loaded_tracks_without_full_scan(monkeypatch, tmp_path: Path) -> None:
    """新成品入库时只索引该文件，搜索查重可立即读取。"""
    source = tmp_path / "library"
    source.mkdir()
    outside = tmp_path / "download.flac"
    outside.write_bytes(b"audio")
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))
    monkeypatch.setattr(service, "get_sources", lambda: [str(source)])
    monkeypatch.setattr(service, "_read_track", lambda path: {
        "id": path.stem,
        "path": str(path),
        "filename": path.name,
        "title": "新歌曲",
        "artist": "歌手",
        "album": "专辑",
        "isrc": None,
    })
    assert service.load_tracks(refresh=True) == []
    version = service.get_index_version()
    output = source / "song.flac"
    output.write_bytes(b"audio")

    assert service.index_output(outside) is False
    assert service.index_output(output) is True
    assert service.get_index_version() == version + 1
    assert [track["title"] for track in service.load_tracks()] == ["新歌曲"]


def test_named_sources_preserve_legacy_paths_and_allow_rename(monkeypatch, tmp_path: Path) -> None:
    """旧路径配置自动显示目录名，新增和修改名称不影响扫描路径。"""
    monkeypatch.setattr(config_manager, "config_dir", tmp_path)
    first = tmp_path / "旧目录"
    second = tmp_path / "第二目录"
    first.mkdir()
    second.mkdir()
    config_manager.save("media_library_sources.json", {"paths": [str(first)]})
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))

    assert service.get_named_sources() == [{"name": "旧目录", "path": str(first)}]
    added = service.add_source("我的收藏", str(second))
    assert added == {"name": "我的收藏", "path": str(second)}
    service.update_source(service.source_id(str(second)), "珍藏", str(second))
    assert service.get_sources() == [str(first), str(second)]
    assert service.get_named_sources()[1]["name"] == "珍藏"


def _track(path: Path) -> dict:
    return {
        "id": path.stem, "path": str(path), "filename": path.name,
        "title": path.stem, "artist": "歌手", "album": "专辑", "isrc": None,
    }


def _pause_background_snapshot(monkeypatch, service):
    ready = threading.Event()
    release = threading.Event()
    deduplicate = service._deduplicate

    def paused(tracks):
        result = deduplicate(tracks)
        if threading.current_thread() is service._refresh_thread:
            ready.set()
            assert release.wait(10), "等待发布后台快照超时"
        return result

    monkeypatch.setattr(service, "_deduplicate", paused)
    return ready, release


def test_snapshot_keeps_its_version_until_background_tracks_are_published(monkeypatch, tmp_path: Path) -> None:
    """后台提交新索引后，尚未替换的旧内存快照必须继续携带旧版本。"""
    source = tmp_path / "library"
    source.mkdir()
    (source / "old.flac").write_bytes(b"old")
    index = FileIndexService(tmp_path / "musicflow.db")
    index.refresh("media_library", [str(source)], _track)
    old_version = index.get_version("media_library")
    service = MediaLibraryService(index)
    monkeypatch.setattr(service, "get_sources", lambda: [str(source)])
    monkeypatch.setattr(service, "_read_track", _track)
    ready, release = _pause_background_snapshot(monkeypatch, service)
    (source / "new.flac").write_bytes(b"new")

    try:
        assert [track["id"] for track in service.load_tracks()] == ["old"]
        assert ready.wait(10), "后台索引没有提交"
        assert index.get_version("media_library") == old_version + 1
        tracks, version = service.load_snapshot()
        assert [track["id"] for track in tracks] == ["old"]
        assert version == old_version
    finally:
        release.set()
        if service._refresh_thread:
            service._refresh_thread.join(10)

    tracks, version = service.load_snapshot()
    assert {track["id"] for track in tracks} == {"old", "new"}
    assert version == old_version + 1


def test_directory_invalidation_rejects_an_old_background_snapshot(monkeypatch, tmp_path: Path) -> None:
    """目录改变使在途扫描失效，不能在清空后重新发布旧目录曲目。"""
    monkeypatch.setattr(config_manager, "config_dir", tmp_path / "config")
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    previous.mkdir()
    current.mkdir()
    (previous / "old.flac").write_bytes(b"old")
    (current / "new.flac").write_bytes(b"new")
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))
    monkeypatch.setattr(service, "_read_track", _track)
    service.save_sources([{"name": "旧目录", "path": str(previous)}])
    service.load_tracks(refresh=True)
    ready, release = _pause_background_snapshot(monkeypatch, service)
    service._schedule_refresh()
    try:
        assert ready.wait(10), "后台索引没有提交"
        service.save_sources([{"name": "新目录", "path": str(current)}])
    finally:
        release.set()
        service._refresh_thread.join(10)

    assert service._tracks == []
    tracks, version = service.load_snapshot()
    assert [track["id"] for track in tracks] == ["new"]
    assert version == service.get_index_version()


def test_index_output_includes_committed_scan_and_rejects_its_late_publish(monkeypatch, tmp_path: Path) -> None:
    """单文件入库取得完整持久快照，较早的后台扫描不能覆盖新成品。"""
    source = tmp_path / "library"
    source.mkdir()
    (source / "old.flac").write_bytes(b"old")
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))
    monkeypatch.setattr(service, "get_sources", lambda: [str(source)])
    monkeypatch.setattr(service, "_read_track", _track)
    service.load_tracks(refresh=True)
    ready, release = _pause_background_snapshot(monkeypatch, service)
    (source / "scanned.flac").write_bytes(b"scanned")
    service._schedule_refresh()
    try:
        assert ready.wait(10), "后台索引没有提交"
        output = source / "output.flac"
        output.write_bytes(b"output")
        assert service.index_output(output)
        assert {track["id"] for track in service.load_tracks()} == {"old", "scanned", "output"}
        version = service.get_index_version()
    finally:
        release.set()
        service._refresh_thread.join(10)

    tracks, snapshot_version = service.load_snapshot()
    assert {track["id"] for track in tracks} == {"old", "scanned", "output"}
    assert snapshot_version == version


def test_explicit_refresh_rejects_an_older_background_publish(monkeypatch, tmp_path: Path) -> None:
    """主动刷新完成后，较早的后台快照不得让内存曲目和版本倒退。"""
    source = tmp_path / "library"
    source.mkdir()
    (source / "old.flac").write_bytes(b"old")
    service = MediaLibraryService(FileIndexService(tmp_path / "musicflow.db"))
    monkeypatch.setattr(service, "get_sources", lambda: [str(source)])
    monkeypatch.setattr(service, "_read_track", _track)
    service.load_tracks(refresh=True)
    ready, release = _pause_background_snapshot(monkeypatch, service)
    service._schedule_refresh()
    try:
        assert ready.wait(10), "后台索引没有提交"
        (source / "new.flac").write_bytes(b"new")
        assert {track["id"] for track in service.load_tracks(refresh=True)} == {"old", "new"}
        version = service.get_index_version()
    finally:
        release.set()
        service._refresh_thread.join(10)

    assert {track["id"] for track in service.load_tracks()} == {"old", "new"}
    assert service.load_snapshot()[1] == version
