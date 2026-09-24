import asyncio
import io
import json

import pytest
from fastapi import HTTPException

from app.api.routes import discovery
from app.models import DeliveryTarget, DeliveryTargetType, WatchFolder
from app.services.musicdl_client import MusicdlClient


def test_apple_precheck_separates_personal_and_public_catalog(monkeypatch) -> None:
    """补齐前分别展示个人资料库和公开曲库，不能把可搜索误认为已添加。"""
    monkeypatch.setattr(discovery.dual_library_service, "find_apple_candidates", lambda _track: [
        {"title": "海阔天空", "artist": "歌手甲"},
    ])
    search_calls = []
    def fake_search(*args):
        search_calls.append(args)
        return [
            {"title": "海阔天空", "artist": "歌手乙", "track_url": "https://music.apple.com/song/1"},
        ]
    monkeypatch.setattr(discovery.apple_catalog_service, "search", fake_search)
    result = asyncio.run(discovery.precheck_apple_fill(
        discovery.ApplePrecheckRequest(selected_track={"song_name": "海阔天空", "singers": "歌手丙"})
    ))
    assert result["personal"][0]["artist"] == "歌手甲"
    assert result["catalog"][0]["artist"] == "歌手乙"
    assert result["catalog_error"] == ""
    assert result["country"] == discovery.dual_library_config.get()["apple_storefront"]
    assert search_calls[0][2] == 20


def test_apple_handoff_requires_review_when_personal_candidate_exists(monkeypatch) -> None:
    """绕过页面直接创建补齐任务时，也不能静默重复上传疑似已有曲目。"""
    monkeypatch.setattr(discovery.dual_library_service, "find_apple_candidates", lambda _track: [
        {"title": "同名歌曲", "artist": "另一位歌手"},
    ])
    created = []
    monkeypatch.setattr(discovery.acquisition_service, "create_job", lambda *_args: created.append(True) or {"id": "job"})
    request = discovery.AcquisitionRequest(selected_track={"song_name": "同名歌曲"}, desired_apple=True)
    with pytest.raises(HTTPException) as error:
        asyncio.run(discovery.create_acquisition(request))
    assert error.value.status_code == 409
    assert not created
    request.allow_possible_duplicate = True
    assert asyncio.run(discovery.create_acquisition(request))["id"] == "job"


def test_musicdl_client_uses_existing_web_api(monkeypatch) -> None:
    """MusicFlow 应连接当前 Musicdl Web 已提供的接口，不能请求不存在的 v1 路由。"""
    client = MusicdlClient()
    json_calls = []
    request_calls = []

    def fake_json(path, method="GET", payload=None):
        json_calls.append((path, method, payload))
        if path == "/api/version":
            return {"version": "1.0.1"}
        return [{"id": "QQMusicClient", "default": True}]

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_request(path, method="GET", payload=None, extra_headers=None):
        request_calls.append(path)
        body = (
            "event: result\n"
            f"data: {json.dumps({'token': 'track-1'}, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        return FakeResponse(body)

    monkeypatch.setattr(client, "_json", fake_json)
    monkeypatch.setattr(client, "_request", fake_request)

    assert client.health() == {"status": "healthy", "version": "1.0.1"}
    assert client.sources() == [{"id": "QQMusicClient", "default": True}]
    assert list(client.search_events("七里香", ["QQMusicClient"])) == [
        ("result", {"token": "track-1"})
    ]
    assert json_calls == [
        ("/api/version", "GET", None),
        ("/api/sources", "GET", None),
    ]
    assert request_calls == [
        "/api/search?q=%E4%B8%83%E9%87%8C%E9%A6%99&sources=QQMusicClient"
    ]


def test_download_settings_are_forwarded_to_musicdl(monkeypatch) -> None:
    """下载目录应原样交给 musicdl 保存，MusicFlow 不另存一份配置。"""
    calls = []

    def fake_json(path, method="GET", payload=None):
        calls.append((path, method, payload))
        return payload

    monkeypatch.setattr(discovery.musicdl_client, "_json", fake_json)
    request = discovery.DownloadSettingsRequest(
        download_directories=[discovery.DownloadDirectory(name="本地", path=r"D:\Music")]
    )

    result = asyncio.run(discovery.update_download_settings(request))

    assert result == {"download_directories": [{"name": "本地", "path": r"D:\Music"}]}
    assert calls == [("/api/settings", "POST", result)]


def test_download_button_creates_musicdl_server_task(monkeypatch) -> None:
    """选择目录后应创建 musicdl 服务器下载任务，而不是直接拉取浏览器文件。"""
    calls = []

    def fake_json(path, method="GET", payload=None):
        calls.append((path, method, payload))
        return {"download_id": "download-1"}

    monkeypatch.setattr(discovery.musicdl_client, "_json", fake_json)
    request = discovery.DownloadRequest(token="track-token", directory_name="本地")

    result = asyncio.run(discovery.create_discovery_download(request))

    assert result == {"download_id": "download-1"}
    assert calls == [
        ("/api/download", "POST", {"token": "track-token", "directory_name": "本地"})
    ]


def test_dual_library_config_selects_independent_watch_folders(monkeypatch) -> None:
    """飞牛与 Apple Music 必须保存不同的监控目录。"""
    nas_folder = WatchFolder(
        id="nas-downloads",
        name="飞牛下载目录",
        input_dir="/music/nas-downloads",
        targets=[DeliveryTarget(type=DeliveryTargetType.COPY, output_dir="/music/library")],
    )
    apple_folder = WatchFolder(
        id="apple-downloads",
        name="Apple 下载目录",
        input_dir="/music/apple-downloads",
        targets=[DeliveryTarget(type=DeliveryTargetType.CONVERT, output_dir="/music/apple", profile_id="apple")],
    )
    profile = type("Profile", (), {"apple_music_handoff_enabled": True, "apple_music_import_dir": "/apple/import"})()
    saved = []
    monkeypatch.setattr(
        discovery.watch_folder_manager,
        "get_watch_folder",
        lambda folder_id: {nas_folder.id: nas_folder, apple_folder.id: apple_folder}.get(folder_id),
    )
    monkeypatch.setattr(discovery.profile_manager, "get_profile", lambda _profile_id: profile)
    monkeypatch.setattr(
        discovery.dual_library_config,
        "save",
        lambda nas_id, apple_id, storefront: saved.append((nas_id, apple_id, storefront))
        or {
            "nas_watch_folder_id": nas_id,
            "apple_watch_folder_id": apple_id,
            "apple_storefront": storefront,
        },
    )

    result = asyncio.run(discovery.update_dual_library_config(discovery.DualLibraryConfigRequest(
        nas_watch_folder_id=nas_folder.id,
        apple_watch_folder_id=apple_folder.id,
    )))

    assert result == {
        "nas_watch_folder_id": nas_folder.id,
        "apple_watch_folder_id": apple_folder.id,
        "apple_storefront": "cn",
    }
    assert saved == [(nas_folder.id, apple_folder.id, "cn")]


def test_search_backfills_presence_before_done(monkeypatch) -> None:
    """索引稍后就绪时，应在搜索结束前回填已返回结果的双库状态。"""
    original_index = discovery.presence_index
    presence = {
        "local_isrc": {"CN123"},
        "local_metadata": set(),
        "apple_isrc": set(),
        "apple_metadata": set(),
    }

    def search_events(_query, _sources):
        yield "result", {
            "token": "track-1",
            "source": "qq",
            "song_name": "歌曲",
            "singers": "歌手",
            "album": "专辑",
            "isrc": "CN123",
        }
        discovery.presence_index = presence
        discovery.presence_index_ready.set()
        yield "done", {"count": 1}

    async def collect_stream():
        response = await discovery.search_discovery(q="歌曲", sources=None)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    monkeypatch.setattr(discovery, "_get_presence_index", lambda: None)
    monkeypatch.setattr(discovery.musicdl_client, "search_events", search_events)
    try:
        stream = asyncio.run(collect_stream())
    finally:
        discovery.presence_index = original_index

    assert stream.index("event: result") < stream.index("event: presence") < stream.index("event: done")
    assert '"nas_present": true' in stream
    assert '"presence_pending": false' in stream
