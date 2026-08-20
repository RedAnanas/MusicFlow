import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import files as files_api


@pytest.fixture(autouse=True)
def restore_files_cache():
    """隔离每个测试使用的文件缓存。"""
    original_files = dict(files_api.files_cache)
    files_api.files_cache.clear()
    yield
    files_api.files_cache.clear()
    files_api.files_cache.update(original_files)


def test_delete_file_removes_source_file(monkeypatch, tmp_path):
    """删除接口应移除音乐源目录内的文件和缓存。"""
    source_dir = tmp_path / "source"
    source_file = source_dir / "album" / "song.flac"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"audio")
    monkeypatch.setattr(files_api.settings, "MUSIC_SOURCE_DIR", str(source_dir))
    files_api.files_cache["file-1"] = {
        "path": str(source_file),
        "filename": source_file.name,
    }

    result = asyncio.run(files_api.delete_file("file-1"))

    assert result == {"status": "success", "deleted": "file-1"}
    assert not source_file.exists()
    assert "file-1" not in files_api.files_cache


def test_delete_file_rejects_path_outside_source_directory(monkeypatch, tmp_path):
    """删除接口不得删除音乐源目录之外的文件。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    outside_file = tmp_path / "outside.flac"
    outside_file.write_bytes(b"audio")
    monkeypatch.setattr(files_api.settings, "MUSIC_SOURCE_DIR", str(source_dir))
    files_api.files_cache["outside"] = {
        "path": str(outside_file),
        "filename": outside_file.name,
    }

    with pytest.raises(HTTPException) as error:
        asyncio.run(files_api.delete_file("outside"))

    assert error.value.status_code == 403
    assert outside_file.exists()
