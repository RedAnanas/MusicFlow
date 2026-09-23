from pathlib import Path

from app.services.file_index_service import FileIndexService


def _reader(calls: list[str]):
    def read(path: Path):
        calls.append(str(path))
        return {
            "id": path.stem,
            "path": str(path),
            "filename": path.name,
            "format": path.suffix.lstrip("."),
            "size": path.stat().st_size,
        }

    return read


def test_index_persists_and_reuses_unchanged_metadata(tmp_path: Path) -> None:
    """服务重启后应直接读取 SQLite，未变化文件不得重复解析元数据。"""
    source = tmp_path / "music"
    source.mkdir()
    song = source / "song.flac"
    song.write_bytes(b"audio")
    database = tmp_path / "musicflow.db"
    calls = []

    first = FileIndexService(database)
    indexed = first.refresh("workspace", [str(source)], _reader(calls))
    restarted = FileIndexService(database)
    persisted = restarted.load("workspace")
    restarted.refresh("workspace", [str(source)], _reader(calls))

    assert indexed == persisted
    assert calls == [str(song)]


def test_index_rereads_only_changed_file(tmp_path: Path) -> None:
    """文件大小或修改时间变化时才重新读取音频信息。"""
    source = tmp_path / "music"
    source.mkdir()
    unchanged = source / "unchanged.flac"
    changed = source / "changed.flac"
    unchanged.write_bytes(b"one")
    changed.write_bytes(b"two")
    calls = []
    service = FileIndexService(tmp_path / "musicflow.db")
    service.refresh("workspace", [str(source)], _reader(calls))
    calls.clear()

    changed.write_bytes(b"changed audio")
    service.refresh("workspace", [str(source)], _reader(calls))

    assert calls == [str(changed)]


def test_unavailable_source_keeps_last_successful_index(tmp_path: Path) -> None:
    """网络目录离线时必须保留上次索引，不能把资料库误判为空。"""
    source = tmp_path / "music"
    source.mkdir()
    song = source / "song.flac"
    song.write_bytes(b"audio")
    service = FileIndexService(tmp_path / "musicflow.db")
    service.refresh("media_library", [str(source)], _reader([]))
    song.unlink()
    source.rmdir()

    retained = service.refresh("media_library", [str(source)], _reader([]))

    assert [item["path"] for item in retained] == [str(song)]


def test_scopes_share_unchanged_file_metadata(tmp_path: Path) -> None:
    """操作台与资料库引用同一文件时不应重复解析音频元数据。"""
    source = tmp_path / "music"
    source.mkdir()
    song = source / "song.flac"
    song.write_bytes(b"audio")
    calls = []
    service = FileIndexService(tmp_path / "musicflow.db")

    service.refresh("workspace", [str(source)], _reader(calls))
    service.refresh("media_library", [str(source)], _reader(calls))

    assert calls == [str(song)]
