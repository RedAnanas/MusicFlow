import asyncio
import threading

import pytest
from fastapi import HTTPException

from app.api.routes import filesystem


def test_get_entries_lists_directories_and_audio_files(tmp_path):
    """目录浏览应返回子目录和支持的音频文件，并隐藏无关文件。"""
    album = tmp_path / "Album"
    album.mkdir()
    audio = tmp_path / "歌曲.flac"
    audio.write_bytes(b"audio")
    (tmp_path / "说明.txt").write_text("text", encoding="utf-8")

    result = asyncio.run(filesystem.get_entries(str(tmp_path), audio_only=True, limit=1000))

    assert result.path == str(tmp_path)
    assert [(entry.name, entry.is_directory) for entry in result.entries] == [
        ("Album", True),
        ("歌曲.flac", False),
    ]


def test_get_entries_rejects_relative_path():
    """服务器文件浏览器不得接受含义不明确的相对路径。"""
    with pytest.raises(HTTPException) as error:
        asyncio.run(filesystem.get_entries("music", audio_only=True, limit=1000))

    assert error.value.status_code == 400


def test_get_entries_runs_directory_io_in_worker_thread(tmp_path, monkeypatch):
    """目录读取应离开 API 事件循环，避免网络共享较慢时阻塞其他请求。"""
    original = filesystem._list_directory
    calling_thread = threading.get_ident()

    def checked_list_directory(path, audio_only, limit):
        assert threading.get_ident() != calling_thread
        return original(path, audio_only, limit)

    monkeypatch.setattr(filesystem, "_list_directory", checked_list_directory)

    result = asyncio.run(filesystem.get_entries(str(tmp_path), audio_only=True, limit=1000))

    assert result.path == str(tmp_path)


def test_get_entries_reports_inaccessible_network_share(monkeypatch):
    """网络共享不可访问时应返回可操作的错误提示。"""
    def missing_share(path, audio_only, limit):
        raise FileNotFoundError(path)

    monkeypatch.setattr(filesystem, "_list_directory", missing_share)

    with pytest.raises(HTTPException) as error:
        asyncio.run(filesystem.get_entries(r"\\feiniu\music", audio_only=True, limit=1000))

    assert error.value.status_code == 404
    assert error.value.detail == "目录不存在，或网络共享尚未连接"
