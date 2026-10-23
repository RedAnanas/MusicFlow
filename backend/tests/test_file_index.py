import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

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


def test_snapshot_reads_tracks_and_version_in_one_sqlite_transaction(monkeypatch, tmp_path: Path) -> None:
    """读取曲目后并发更新索引，返回版本仍必须属于同一份曲目。"""
    source = tmp_path / "music"
    source.mkdir()
    song = source / "song.flac"
    song.write_bytes(b"audio")
    service = FileIndexService(tmp_path / "musicflow.db")
    previous = service.refresh("media_library", [str(source)], _reader([]))
    version = service.get_version("media_library")
    with service._connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    tracks_read = threading.Event()
    version_read = threading.Event()
    original_version = service._version_in_connection

    def paused_version(connection, scope):
        tracks_read.set()
        assert version_read.wait(10), "等待读取快照版本超时"
        return original_version(connection, scope)

    monkeypatch.setattr(service, "_version_in_connection", paused_version)
    writer = FileIndexService(service.database_path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: service.load_snapshot("media_library"))
        try:
            assert tracks_read.wait(10), "快照曲目没有读取"
            writer.upsert("media_library", str(source), {**previous[0], "title": "更新的标题"})
        finally:
            version_read.set()
        tracks, snapshot_version = future.result(timeout=10)

    assert tracks == previous
    assert snapshot_version == version
    assert writer.get_version("media_library") == version + 1


@pytest.mark.parametrize("legacy_database", [False, True], ids=["新数据库", "已有数据库升级"])
def test_cross_scope_metadata_lookup_uses_path_index_without_changing_results(tmp_path: Path, legacy_database: bool) -> None:
    """新建和升级数据库均按路径检索跨库元数据，且保留已有曲目与版本。"""
    source = tmp_path / "music"
    source.mkdir()
    song = source / "song.flac"
    song.write_bytes(b"audio")
    calls = []
    service = FileIndexService(tmp_path / "musicflow.db")
    expected = service.refresh("workspace", [str(source)], _reader(calls))
    version = service.get_version("workspace")
    if legacy_database:
        with service._connect() as connection:
            connection.execute("DROP INDEX IF EXISTS idx_file_index_path")

    restarted = FileIndexService(service.database_path)
    assert restarted.refresh("media_library", [str(source)], _reader(calls)) == expected
    assert restarted.load("workspace") == expected
    assert restarted.get_version("workspace") == version
    assert calls == [str(song)]
    stat = song.stat()
    with restarted._connect() as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT data_json FROM file_index "
            "WHERE path = ? AND size = ? AND mtime_ns = ? LIMIT 1",
            (str(song), stat.st_size, stat.st_mtime_ns),
        ).fetchall()

    assert any("SEARCH" in row["detail"] and "idx_file_index_path" in row["detail"] for row in plan), [dict(row) for row in plan]
