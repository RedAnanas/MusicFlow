import asyncio
from contextlib import nullcontext

import pytest

from app.api.routes import system
from app.services.config_manager import config_manager
from app.services.musicdl_client import MusicdlClient, MusicdlClientError


def test_musicdl_connection_url_is_persisted_and_reloaded(monkeypatch, tmp_path):
    """系统状态保存的服务地址应在新客户端中继续生效。"""
    monkeypatch.setattr(config_manager, "config_dir", tmp_path)
    monkeypatch.setattr(system.musicdl_client, "base_url", "http://127.0.0.1:5000")

    result = asyncio.run(system.update_musicdl_connection(system.MusicdlConnectionUpdate(
        base_url="http://musicdl-web:5000/",
    )))

    assert result == {"base_url": "http://musicdl-web:5000"}
    assert MusicdlClient().base_url == "http://musicdl-web:5000"
    assert system.musicdl_client.base_url == "http://musicdl-web:5000"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:pass@host:5000", "http://host:5000/api", "http://host:5000?q=1", "http://host:5000?"])
def test_musicdl_connection_rejects_unsupported_urls(monkeypatch, tmp_path, url):
    """服务地址只能是无凭据、无附加路径的 HTTP 根地址。"""
    monkeypatch.setattr(config_manager, "config_dir", tmp_path)

    with pytest.raises(ValueError):
        system.save_musicdl_base_url(url)


def test_musicdl_connection_status_distinguishes_legacy_download(monkeypatch):
    """已连接旧版 musicdl 时应提示一键补齐接口不兼容。"""
    monkeypatch.setattr(system.musicdl_client, "base_url", "http://musicdl-web:5000")
    monkeypatch.setattr(MusicdlClient, "health", lambda self: {"status": "healthy", "version": "1.0.2"})
    monkeypatch.setattr(MusicdlClient, "supports_acquisition", lambda self: False)

    result = asyncio.run(system.get_musicdl_connection())

    assert result == {
        "base_url": "http://musicdl-web:5000",
        "connected": True,
        "version": "1.0.2",
        "acquisition_supported": False,
        "error": None,
    }


def test_musicdl_acquisition_probe_checks_v1_route(monkeypatch):
    """一键补齐能力检查只探测接口，不创建下载任务。"""
    client = MusicdlClient(base_url="http://musicdl-web:5000")
    requests = []

    def available(path, method="GET"):
        requests.append((path, method))
        return nullcontext()

    monkeypatch.setattr(client, "_request", available)
    assert client.supports_acquisition() is True
    assert requests == [("/api/v1/downloads", "OPTIONS")]

    def unavailable(path, method="GET"):
        raise MusicdlClientError("Not Found")

    monkeypatch.setattr(client, "_request", unavailable)
    assert client.supports_acquisition() is False
