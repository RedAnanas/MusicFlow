"""对账缓存构建、发布和失效的并发回归。"""

import asyncio
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from app.api.routes import library
from app.services.dual_library_service import DualLibraryService


@pytest.fixture
def reconciliation(monkeypatch, tmp_path):
    service = DualLibraryService(tmp_path / 'cache.db')
    snapshot, _ = service.import_snapshot('library.csv', (
        'Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n'
        '云端歌曲,云端歌手,云端专辑,资料库,Apple Music,,123\n'
    ).encode())
    tracks = [{'id': 'local', 'path': '/fixture/local.flac', 'filename': 'local.flac',
               'title': '本地歌曲', 'artist': '本地歌手', 'album': '本地专辑'}]
    media = SimpleNamespace(get_sources=lambda: ['/fixture'], load_tracks=lambda _refresh: tracks,
                            get_index_version=lambda: 1, load_snapshot=lambda _refresh: (tracks, 1))
    monkeypatch.setattr(library, 'dual_library_service', service)
    monkeypatch.setattr(library, 'media_library_service', media)
    monkeypatch.setattr(library, 'reconciliation_cache', None)
    monkeypatch.setattr(library, '_reconciliation_generation', 0, raising=False)
    return service, tracks, snapshot


async def query(expected_revision=None):
    return await library.get_library_reconciliation(status=None, search=None, refresh_local=False,
                                                   offset=0, limit=100, expected_revision=expected_revision)


async def wait_for(event):
    assert await asyncio.to_thread(event.wait, 5), '并发测试未进入预期阶段'


def confirm(service, tracks):
    key = service.get_latest_snapshot()['id']
    with service._connect() as connection:
        key = connection.execute('SELECT track_key FROM apple_snapshot_rows WHERE snapshot_id = ?', (key,)).fetchone()[0]
    service.save_match_decision(tracks[0]['id'], key, 'confirmed')


def test_失效期间的旧计算不得重新发布到内存或持久缓存(reconciliation, monkeypatch):
    service, tracks, snapshot = reconciliation
    built, release = Event(), Event()
    original = service.reconcile

    def paused_reconcile(local):
        result = original(local)
        built.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(service, 'reconcile', paused_reconcile)

    async def run():
        request = asyncio.create_task(query())
        try:
            await wait_for(built)
            await asyncio.to_thread(confirm, service, tracks)
            await asyncio.to_thread(library.invalidate_reconciliation_cache)
        finally:
            release.set()
        response = await request
        assert response['summary']['both'] == 1
        assert service.get_cached_reconciliation(snapshot['id'], 1)['summary']['both'] == 1
        library.reconciliation_cache = None
        assert (await query())['summary']['both'] == 1

    asyncio.run(run())


def test_持久缓存写入与失效协调且不残留已失效结果(reconciliation, monkeypatch):
    service, tracks, snapshot = reconciliation
    writing, release, invalidating = Event(), Event(), Event()
    original_save = service.save_cached_reconciliation

    def paused_save(*args):
        writing.set()
        assert release.wait(5)
        original_save(*args)

    def invalidate():
        invalidating.set()
        library.invalidate_reconciliation_cache()

    monkeypatch.setattr(service, 'save_cached_reconciliation', paused_save)

    async def run():
        request = asyncio.create_task(query())
        invalidation = None
        try:
            await wait_for(writing)
            await asyncio.to_thread(confirm, service, tracks)
            invalidation = asyncio.create_task(asyncio.to_thread(invalidate))
            await wait_for(invalidating)
        finally:
            release.set()
        await request
        await invalidation
        assert (await query())['summary']['both'] == 1
        assert service.get_cached_reconciliation(snapshot['id'], 1)['summary']['both'] == 1

    asyncio.run(run())


def test_并发首次对账只构建一次并复用版本供候选翻页(reconciliation, monkeypatch):
    service, _, _ = reconciliation
    entered, second_entered, release = Event(), Event(), Event()
    counter_lock = Lock()
    calls = 0
    original = service.reconcile

    def paused_reconcile(local):
        nonlocal calls
        with counter_lock:
            calls += 1
            if calls > 1:
                second_entered.set()
        entered.set()
        assert release.wait(5)
        return original(local)

    monkeypatch.setattr(service, 'reconcile', paused_reconcile)

    async def run():
        first = asyncio.create_task(query())
        second = None
        try:
            await wait_for(entered)
            second = asyncio.create_task(query())
            await asyncio.to_thread(second_entered.wait, 0.2)
        finally:
            release.set()
        responses = await asyncio.gather(first, second)
        assert calls == 1
        assert responses[0]['revision'] == responses[1]['revision']
        assert (await query(responses[0]['revision']))['entries'] == responses[0]['entries']

    asyncio.run(run())


def test_路由只按曲目快照自身版本缓存并在新快照发布后更新(reconciliation):
    service, tracks, snapshot = reconciliation
    library.media_library_service.get_index_version = lambda: 2

    async def run():
        first = await query()
        assert library.reconciliation_cache['local_index_version'] == 1
        assert first['summary']['both'] == 0
        assert service.get_cached_reconciliation(snapshot['id'], 2) is None
        updated = tracks + [{'id': 'new', 'path': '/fixture/new.flac', 'filename': 'new.flac',
                             'title': '云端歌曲', 'artist': '云端歌手', 'album': '云端专辑'}]
        library.media_library_service.load_snapshot = lambda _refresh: (updated, 2)
        second = await query()
        assert second['revision'] != first['revision']
        assert second['summary']['both'] == 1
        assert service.get_cached_reconciliation(snapshot['id'], 2)['summary']['both'] == 1

    asyncio.run(run())
