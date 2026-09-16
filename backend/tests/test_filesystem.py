import asyncio

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
