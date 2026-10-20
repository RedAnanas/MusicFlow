import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from types import SimpleNamespace

from app.api.routes import files as files_api


@pytest.fixture
def playback(monkeypatch, tmp_path):
    """使用独立来源与音频缓存验证播放响应状态、响应头和音频内容。"""
    source = tmp_path / "music"
    source.mkdir()
    audio = source / "song.m4a"
    audio.write_bytes(b"0123456789")
    monkeypatch.setattr(files_api, "files_cache", {"song": {"path": str(audio)}})
    monkeypatch.setattr(files_api, "_load_library_sources", lambda: [str(source)])
    class PlaybackClient:
        def get(self, url, headers=None, method="GET"):
            async def request():
                file_id = url.split("/")[2]
                try:
                    if url.endswith("/lyrics"):
                        data = await files_api.get_file_lyrics(file_id)
                        return SimpleNamespace(status_code=200, json=lambda: data)
                    scope = {"type": "http", "method": method, "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]}
                    response = await files_api.stream_file(file_id, Request(scope))
                    body = b"".join([part async for part in response.body_iterator]) if hasattr(response, "body_iterator") else response.body
                    return SimpleNamespace(status_code=response.status_code, headers=response.headers, content=body)
                except HTTPException as error:
                    return SimpleNamespace(status_code=error.status_code)
            return asyncio.run(request())

        def head(self, url):
            return self.get(url, method="HEAD")

    yield PlaybackClient(), audio


def test_本地播放完整响应与音频类型(playback):
    client, _ = playback
    result = client.get("/files/song/stream")
    assert result.status_code == 200
    assert result.content == b"0123456789"
    assert result.headers["content-type"] == "audio/mp4"
    assert result.headers["accept-ranges"] == "bytes"
    head = client.head("/files/song/stream")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == "10"


@pytest.mark.parametrize("value,expected", [("bytes=2-5", b"2345"), ("bytes=7-", b"789"), ("bytes=-3", b"789"), ("bytes=8-99", b"89")])
def test_本地播放支持拖动与尾部范围请求(playback, value, expected):
    client, _ = playback
    result = client.get("/files/song/stream", headers={"Range": value})
    assert result.status_code == 206
    assert result.content == expected
    assert int(result.headers["content-length"]) == len(expected)
    assert result.headers["content-range"].endswith("/10")


@pytest.mark.parametrize("value", ["bytes=10-", "bytes=5-2", "bytes=-0", "bytes=-", "bytes=0-1,3-4", "bytes=" + "9" * 5000 + "-", "invalid"])
def test_无效播放范围返回文件长度(playback, value):
    client, _ = playback
    result = client.get("/files/song/stream", headers={"Range": value})
    assert result.status_code == 416
    assert result.headers["content-range"] == "bytes */10"


def test_播放拒绝未知文件越界文件与非音频(playback, monkeypatch, tmp_path):
    client, audio = playback
    assert client.get("/files/missing/stream").status_code == 404
    outside = tmp_path / "private.mp3"
    outside.write_bytes(b"private")
    monkeypatch.setitem(files_api.files_cache, "outside", {"path": str(outside)})
    assert client.get("/files/outside/stream").status_code == 403
    text = audio.with_suffix(".txt")
    text.write_text("private", encoding="utf-8")
    monkeypatch.setitem(files_api.files_cache, "text", {"path": str(text)})
    assert client.get("/files/text/stream").status_code == 415
    audio.unlink()
    assert client.get("/files/song/stream").status_code == 404


def test_歌词响应不包含封面(playback, monkeypatch):
    client, _ = playback
    monkeypatch.setattr(files_api.metadata_service, "read_metadata", lambda _: {"lyrics": "[00:01]歌词", "cover": {"data": b"\xff"}})
    assert client.get("/files/song/lyrics").json() == {"lyric": "[00:01]歌词"}
    assert client.get("/files/missing/lyrics").status_code == 404
