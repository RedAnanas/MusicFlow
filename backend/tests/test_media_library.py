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
