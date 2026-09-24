import asyncio
from pathlib import Path

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
