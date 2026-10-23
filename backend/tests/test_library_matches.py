import asyncio
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException

from app.api.routes import library
from app.services.dual_library_service import DualLibraryService


def test_apple_only_confirmation_consumes_local_only_candidate(monkeypatch, tmp_path: Path) -> None:
    """仅 Apple Music 有只能与当前仅本地有的歌曲确认，确认后两侧合为双库都有。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    service.import_snapshot(
        "library.csv",
        (
            "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"
            "Apple歌曲甲,歌手甲,专辑,资料库,Apple Music,,1001\n"
            "Apple歌曲乙,歌手乙,专辑,资料库,Apple Music,,1002\n"
        ).encode("utf-8"),
    )
    local_tracks = [{"id": "local-1", "path": "/music/a.flac", "filename": "a.flac", "title": "本地歌曲", "artist": "歌手丙"}]
    monkeypatch.setattr(library, "dual_library_service", service)
    monkeypatch.setattr(library.media_library_service, "load_tracks", lambda _refresh: local_tracks)
    monkeypatch.setattr(library, "invalidate_reconciliation_cache", lambda: None)

    before = service.reconcile(local_tracks)
    apple_only = [entry for entry in before["entries"] if entry["status"] == "apple_only"]
    assert before["summary"] == {"both": 0, "nas_only": 1, "apple_only": 2, "review": 0}

    request = library.MatchDecisionRequest(
        local_file_id="local-1", apple_track_key=apple_only[0]["apple"]["track_key"],
        decision="confirmed", require_only_unmatched=True,
    )
    asyncio.run(library.save_library_match(request))
    after = service.reconcile(local_tracks)
    assert after["summary"] == {"both": 1, "nas_only": 0, "apple_only": 1, "review": 0}
    assert next(entry for entry in after["entries"] if entry["status"] == "both")["match_reason"] == "manual_confirmed"

    request.apple_track_key = apple_only[1]["apple"]["track_key"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(library.save_library_match(request))
    assert error.value.status_code == 409
    assert service.reconcile(local_tracks)["summary"] == after["summary"]


def test_incremental_link_routes_validate_current_snapshot_and_invalidate_caches(monkeypatch, tmp_path: Path) -> None:
    """人工关联完成后失效查重与对账缓存，失效目标返回冲突且不写关联。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track({"title": "记录原名", "artist": "歌手"}, "manual")
    service.import_snapshot("library.csv", (
        "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"
        "快照曲名,歌手,专辑,资料库,Apple Music,,123\n"
    ).encode())
    invalidated = []
    monkeypatch.setattr(library, "dual_library_service", service)
    monkeypatch.setattr(library, "invalidate_presence_index", lambda: invalidated.append("presence"))
    monkeypatch.setattr(library, "invalidate_reconciliation_cache", lambda: invalidated.append("reconciliation"))
    review = asyncio.run(library.review_apple_incremental_entry(entry["id"], "快照曲名"))
    key = review["candidates"][0]["track_key"]
    request = library.IncrementalSnapshotLinkRequest(track_key=key)
    asyncio.run(library.link_apple_incremental_entry(entry["id"], request))
    assert invalidated == ["presence", "reconciliation"]
    request.track_key = "stale-key"
    with pytest.raises(HTTPException) as error:
        asyncio.run(library.link_apple_incremental_entry(entry["id"], request))
    assert error.value.status_code == 409
    assert service.list_incremental_tracks()[0]["linked_track_key"] == key
    with pytest.raises(HTTPException) as error:
        asyncio.run(library.review_apple_incremental_entry("missing", ""))
    assert error.value.status_code == 404


def test_incremental_merge_route_invalidates_caches_and_rejects_stale_records(monkeypatch, tmp_path: Path) -> None:
    """合并成功后刷新两类缓存，重复请求返回冲突而非误合并其他记录。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    first = service.upsert_incremental_track({"title": "歌曲", "artist": "歌手"}, "manual")
    second = service.upsert_incremental_track({"title": "歌曲 (DJ版)", "artist": "歌手"}, "handoff")
    invalidated = []
    monkeypatch.setattr(library, "dual_library_service", service)
    monkeypatch.setattr(library, "invalidate_presence_index", lambda: invalidated.append("presence"))
    monkeypatch.setattr(library, "invalidate_reconciliation_cache", lambda: invalidated.append("reconciliation"))
    request = library.IncrementalMergeRequest(source_id=second["id"])
    asyncio.run(library.merge_apple_incremental_entries(first["id"], request))
    assert invalidated == ["presence", "reconciliation"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(library.merge_apple_incremental_entries(first["id"], request))
    assert error.value.status_code == 409


def test_对账版本在翻页时复用并在索引或匹配变化后失效(monkeypatch, tmp_path):
    service = DualLibraryService(tmp_path / 'revision.db')
    service.import_snapshot('library.csv', ('Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n歌曲,歌手,专辑,资料库,Apple Music,,123\n').encode())
    monkeypatch.setattr(library, 'dual_library_service', service)
    monkeypatch.setattr(library, 'reconciliation_cache', None)
    monkeypatch.setattr(library.media_library_service, 'get_sources', lambda: [{}])
    monkeypatch.setattr(library.media_library_service, 'load_snapshot', lambda _refresh: ([], 1))

    def reconcile(expected_revision=None):
        return asyncio.run(library.get_library_reconciliation(status=None, search=None, refresh_local=False,
                                                               offset=0, limit=100, expected_revision=expected_revision))

    first = reconcile()
    assert reconcile()['revision'] == first['revision']
    monkeypatch.setattr(library.media_library_service, 'load_snapshot', lambda _refresh: ([], 2))
    second = reconcile()
    assert second['revision'] != first['revision']
    with pytest.raises(HTTPException) as error:
        reconcile(first['revision'])
    assert error.value.status_code == 409
    library.invalidate_reconciliation_cache()
    assert reconcile()['revision'] != second['revision']


def test_并发人工确认同一本地候选仅一个成功且另一个返回冲突(monkeypatch, tmp_path):
    service = DualLibraryService(tmp_path / 'concurrent.db')
    service.import_snapshot('library.csv', (
        'Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n'
        '云端歌曲甲,歌手甲,专辑甲,资料库,Apple Music,,1001\n'
        '云端歌曲乙,歌手乙,专辑乙,资料库,Apple Music,,1002\n'
    ).encode())
    tracks = [{'id': 'local', 'path': '/fixture/local.flac', 'filename': 'local.flac',
               'title': '独立本地录音', 'artist': '本地歌手', 'album': '本地专辑'}]
    keys = [entry['apple']['track_key'] for entry in service.reconcile(tracks)['entries'] if entry['status'] == 'apple_only']
    assert len(keys) == 2
    monkeypatch.setattr(library, 'dual_library_service', service)
    monkeypatch.setattr(library.media_library_service, 'load_tracks', lambda _refresh: tracks)
    monkeypatch.setattr(library, 'reconciliation_cache', None)
    original_save = service.save_match_decision
    barrier = Barrier(2)

    def simultaneous_save(*args, **kwargs):
        barrier.wait(timeout=5)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(service, 'save_match_decision', simultaneous_save)

    async def run():
        return await asyncio.gather(*[
            library.save_library_match(library.MatchDecisionRequest(local_file_id='local', apple_track_key=key,
                                                                    decision='confirmed', require_only_unmatched=True))
            for key in keys
        ], return_exceptions=True)

    outcomes = asyncio.run(run())
    assert sum(isinstance(outcome, dict) and outcome.get('status') == 'success' for outcome in outcomes) == 1
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, HTTPException)]
    assert len(conflicts) == 1 and conflicts[0].status_code == 409
    assert service.reconcile(tracks)['summary']['both'] == 1
