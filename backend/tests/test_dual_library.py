import csv
import io
import json
from pathlib import Path

import pytest

from app.services.dual_library_service import DualLibraryService, normalize_text


CSV_HEADER = "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"


def test_file_metadata_reuses_acquisition_record_without_merging_other_versions(tmp_path: Path) -> None:
    """同一任务的文件标签复用原记录，名称不同的其他任务仍独立保留。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    original = service.upsert_incremental_track({"title": "预谋 (DJ版)", "artist": "DJ", "album": "专辑"}, "handoff", "job-1")
    service.confirm_incremental_track(original["id"])
    service.record_incremental_file({"title": "预谋", "artist": "DJ", "album": "专辑"}, "direct_upload", ["job-1"])
    assert service.lookup_presence({"title": "预谋", "artist": "DJ", "album": "专辑"}, service.build_presence_index([]))["apple_present"]
    service.upsert_incremental_track({"title": "预谋 (DJ版)", "artist": "DJ", "album": "专辑"}, "direct_upload", "job-1")
    service.import_snapshot("library.csv", (CSV_HEADER + "预谋,DJ,专辑,资料库,Apple Music,,123\n").encode())
    entries = service.list_incremental_tracks()
    assert len(entries) == 1
    assert entries[0]["id"] == original["id"]
    assert entries[0]["manual_confirmed_at"]
    assert entries[0]["snapshot_status"] == "matched"
    assert entries[0]["metadata_variants"][0]["title"] == "预谋"
    service.upsert_incremental_track({"title": "预谋 (现场版)", "artist": "DJ", "album": "专辑"}, "handoff", "job-2")
    assert len(service.list_incremental_tracks()) == 2


def test_merge_incremental_records_keeps_confirmation_history_and_pairing(tmp_path: Path) -> None:
    """人工合并只归并记录，保留原名称、人工确认和已有本地配对。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    source = service.upsert_incremental_track({"title": "预谋 (DJ版)", "artist": "DJ", "album": "专辑"}, "handoff", "job-1")
    target = service.upsert_incremental_track({"title": "预谋", "artist": "DJ", "album": "专辑"}, "direct_upload")
    service.confirm_incremental_track(source["id"])
    service.save_match_decision("local-1", "incremental:" + source["id"], "confirmed")
    service.merge_incremental_tracks(target["id"], source["id"])
    entries = service.list_incremental_tracks()
    assert len(entries) == 1
    assert entries[0]["id"] == target["id"]
    assert entries[0]["manual_confirmed_at"]
    assert entries[0]["acquisition_job_id"] == "job-1"
    assert entries[0]["metadata_variants"][0]["title"] == "预谋 (DJ版)"
    with service._connect() as db:
        assert db.execute("SELECT apple_track_key FROM library_matches").fetchone()[0] == "incremental:" + target["id"]
        assert db.execute("SELECT merged_into FROM apple_incremental_entries WHERE id=?", (source["id"],)).fetchone()[0] == target["id"]
    with pytest.raises(ValueError):
        service.merge_incremental_tracks(target["id"], source["id"])
    repeated = service.upsert_incremental_track({"title": "预谋 (DJ版)", "artist": "DJ", "album": "专辑"}, "handoff", "job-1")
    assert repeated["id"] == target["id"]
    assert len(service.list_incremental_tracks()) == 1
    assert service.lookup_presence({"title": "预谋 (DJ版)", "artist": "DJ", "album": "专辑"}, service.build_presence_index([]))["apple_present"]
    service.delete_incremental_track(target["id"])
    assert service.list_incremental_tracks() == []
    with service._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM apple_incremental_entries").fetchone()[0] == 0


def test_merge_conflicting_records_is_atomic(tmp_path: Path) -> None:
    """不同强标识不能合并，拒绝后两条记录保持完整。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    source = service.upsert_incremental_track({"title": "歌曲", "artist": "歌手", "apple_id": "123"}, "catalog")
    target = service.upsert_incremental_track({"title": "歌曲", "artist": "歌手", "apple_id": "456"}, "catalog")
    with pytest.raises(ValueError, match="不同"):
        service.merge_incremental_tracks(target["id"], source["id"])
    assert len(service.list_incremental_tracks()) == 2


def test_merge_conflicting_local_decisions_is_atomic(tmp_path: Path) -> None:
    """本地配对相互冲突时不能悄悄覆盖人工结论。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    source = service.upsert_incremental_track({"title": "歌曲 (DJ版)", "artist": "歌手"}, "handoff")
    target = service.upsert_incremental_track({"title": "歌曲", "artist": "歌手"}, "direct_upload")
    for entry, local in ((source, "local-1"), (target, "local-2")):
        service.confirm_incremental_track(entry["id"])
        service.save_match_decision(local, "incremental:" + entry["id"], "confirmed")
    with pytest.raises(ValueError, match="本地配对不同"):
        service.merge_incremental_tracks(target["id"], source["id"])
    assert len(service.list_incremental_tracks()) == 2
    with service._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM library_matches").fetchone()[0] == 2


def create_service(tmp_path: Path) -> DualLibraryService:
    return DualLibraryService(tmp_path / "musicflow.db")


def test_reconciliation_result_persists_by_snapshot_and_index_version(tmp_path: Path) -> None:
    """部署重启后应按快照和本地索引版本复用对账结果。"""
    service = create_service(tmp_path)
    result = {"summary": {"both": 1}, "entries": [{"id": "track-1"}]}

    service.save_cached_reconciliation("snapshot-1", 3, result)
    restarted = DualLibraryService(service.database_path)

    assert restarted.get_cached_reconciliation("snapshot-1", 3) == result
    assert restarted.get_cached_reconciliation("snapshot-1", 4) is None


def test_old_reconciliation_cache_is_recomputed_after_matching_rule_change(tmp_path: Path) -> None:
    """旧规则缓存不得掩盖升级后的匹配结果。"""
    service = create_service(tmp_path)
    service.initialize()
    with service._connect() as connection:
        connection.execute(
            "INSERT INTO reconciliation_results VALUES (?, ?, ?, ?)",
            ("snapshot-1", 3, json.dumps({"summary": {}, "entries": []}), "2026-09-24T00:00:00+00:00"),
        )
    assert service.get_cached_reconciliation("snapshot-1", 3) is None


def test_import_snapshot_classifies_rows_and_is_idempotent(tmp_path: Path) -> None:
    """CSV 导入应正确分类，重复内容不得创建新快照。"""
    service = create_service(tmp_path)
    content = (
        CSV_HEADER
        + "上传歌曲,测试歌手,上传专辑,Library Songs,Favorite,,i.uploaded\n"
        + "目录歌曲,目录歌手,目录专辑,Library Songs,Favorite,CNABC1234567,123456\n"
    ).encode("utf-8")

    snapshot, created = service.import_snapshot("library.csv", content)
    repeated, repeated_created = service.import_snapshot("renamed.csv", content)

    assert created is True
    assert repeated_created is False
    assert repeated["id"] == snapshot["id"]
    assert snapshot["row_count"] == 2
    assert snapshot["catalog_count"] == 1
    assert snapshot["uploaded_count"] == 1
    assert snapshot["isrc_count"] == 1


def test_incremental_apple_track_is_used_for_presence_and_confirmed_by_snapshot(tmp_path: Path) -> None:
    """手动新增曲目应立即参与查重，并在后续 CSV 中自动转为已确认。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"apple_id": "12345", "title": "新歌", "artist": "歌手", "album": "新专辑"},
        "catalog",
    )

    index = service.build_presence_index([])
    presence = service.lookup_presence(
        {"song_name": "新歌", "singers": "歌手", "album": "新专辑"},
        index,
    )

    assert entry["verification_status"] == "pending"
    assert presence["apple_present"] is True
    assert presence["apple_pending"] is True

    service.import_snapshot(
        "library.csv",
        (
            "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"
            "新歌,歌手,新专辑,资料库,Apple Music,,12345\n"
        ).encode("utf-8"),
    )

    confirmed = service.list_incremental_tracks()[0]
    assert confirmed["verification_status"] == "confirmed"
    assert confirmed["confirmed_at"]


def test_deleting_snapshot_keeps_manual_incremental_tracks(tmp_path: Path) -> None:
    """删除 CSV 快照不应删除用户单独维护的 Apple Music 增量信息。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    service.upsert_incremental_track(
        {"title": "手工歌曲", "artist": "歌手", "album": ""},
        "manual",
    )
    snapshot, _ = service.import_snapshot(
        "library.csv",
        (
            "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"
            "快照歌曲,歌手,专辑,资料库,Apple Music,,999\n"
        ).encode("utf-8"),
    )

    service.delete_snapshot(snapshot["id"])

    entries = service.list_incremental_tracks()
    assert len(entries) == 1
    assert entries[0]["title"] == "手工歌曲"


def test_manual_confirmation_is_distinct_from_csv_confirmation(tmp_path: Path) -> None:
    """手动确认后参与查重，后续 CSV 匹配才标记为快照确认。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"apple_id": "12345", "title": "新歌", "artist": "歌手", "album": "新专辑"}, "manual"
    )

    confirmed = service.confirm_incremental_track(entry["id"])
    assert confirmed["verification_status"] == "manual_confirmed"
    index = service.build_presence_index([])
    presence = service.lookup_presence(
        {"song_name": "新歌", "singers": "歌手", "album": "新专辑"}, index
    )
    assert presence["apple_present"] is True
    assert presence["apple_pending"] is False

    service.import_snapshot(
        "library.csv",
        (
            "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"
            "新歌,歌手,新专辑,资料库,Apple Music,,12345\n"
        ).encode("utf-8"),
    )
    assert service.list_incremental_tracks()[0]["verification_status"] == "confirmed"


def test_replacing_snapshot_rechecks_incremental_evidence(tmp_path: Path) -> None:
    """A 被 B 更新后，只有 B 中的曲目保留快照确认，人工确认仍独立有效。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    manual = service.upsert_incremental_track(
        {"apple_id": "100", "title": "手动曲目", "artist": "歌手", "album": "专辑"}, "manual"
    )
    service.confirm_incremental_track(manual["id"])
    automatic = service.upsert_incremental_track(
        {"apple_id": "200", "title": "自动曲目", "artist": "歌手", "album": "专辑"}, "handoff"
    )
    first, _ = service.import_snapshot(
        "a.csv",
        (CSV_HEADER + "手动曲目,歌手,专辑,资料库,Apple Music,,100\n自动曲目,歌手,专辑,资料库,Apple Music,,200\n").encode(),
    )
    assert {entry["verification_status"] for entry in service.list_incremental_tracks()} == {"confirmed"}

    second, created = service.import_snapshot(
        "b.csv", (CSV_HEADER + "另一首,歌手,,资料库,Apple Music,,300\n").encode(), first["id"]
    )
    assert created is True
    assert service.get_latest_snapshot()["id"] == second["id"]
    assert {entry["title"]: entry["verification_status"] for entry in service.list_incremental_tracks()} == {
        "手动曲目": "manual_confirmed", "自动曲目": "absent"
    }
    index = service.build_presence_index([])
    presence = service.lookup_presence({"song_name": "自动曲目", "singers": "歌手", "album": "专辑"}, index)
    assert presence["apple_present"] is False
    assert presence["apple_pending"] is False
    service.confirm_incremental_track(manual["id"])
    assert service.list_incremental_tracks()[0]["verification_status"] == "manual_confirmed"
    service.delete_snapshot(second["id"])
    assert service.get_latest_snapshot() is None
    assert {entry["title"]: entry["verification_status"] for entry in service.list_incremental_tracks()} == {
        "手动曲目": "manual_confirmed", "自动曲目": "pending"
    }


def test_delete_a_then_import_unrelated_b_drops_a_confirmation(tmp_path: Path) -> None:
    """删除 A 后导入完全不同的 B，旧 CSV 确认不能继续参与查重。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"apple_id": "100", "title": "旧歌曲", "artist": "歌手", "album": "旧专辑"}, "catalog"
    )
    first, _ = service.import_snapshot(
        "a.csv", (CSV_HEADER + "旧歌曲,歌手,旧专辑,资料库,Apple Music,,100\n").encode()
    )
    assert service.list_incremental_tracks()[0]["verification_status"] == "confirmed"

    service.delete_snapshot(first["id"])
    assert service.list_incremental_tracks()[0]["verification_status"] == "pending"
    service.import_snapshot(
        "b.csv", (CSV_HEADER + "新歌曲,歌手,新专辑,资料库,Apple Music,,200\n").encode()
    )
    assert service.list_incremental_tracks()[0]["verification_status"] == "absent"
    assert service.lookup_presence(
        {"song_name": "旧歌曲", "singers": "歌手", "album": "旧专辑"},
        service.build_presence_index([]),
    )["apple_present"] is False


def test_new_snapshot_preserves_manual_evidence_and_reports_mismatch(tmp_path: Path) -> None:
    """新快照未匹配时保留人工确认与查重依据，独立显示差异。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"title": "离开我的依赖 (DJ铁柱版)", "artist": "王艳薇", "album": "原专辑"}, "direct_upload"
    )
    confirmed = service.confirm_incremental_track(entry["id"])
    service.import_snapshot("new.csv", (CSV_HEADER + "另一首,其他歌手,专辑,资料库,Apple Music,,123\n").encode())

    result = service.list_incremental_tracks()[0]
    assert result["manual_confirmed_at"] == confirmed["manual_confirmed_at"]
    assert result["verification_status"] == "manual_confirmed"
    assert result["snapshot_status"] == "unmatched"
    assert result["matched_track"] is None
    presence = service.lookup_presence(entry, service.build_presence_index([]))
    assert presence["apple_present"] is True
    assert presence["apple_pending"] is False


def test_incremental_snapshot_link_survives_updates_without_merging_names(tmp_path: Path) -> None:
    """人工关联复用稳定曲目标识，记录原名保持不变，近似项不自动确认。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"title": "冬眠2023 (DJ阿布版)", "artist": "DJ阿智、DJ阿布", "album": "旧专辑"}, "direct_upload"
    )
    first, _ = service.import_snapshot(
        "first.csv", (CSV_HEADER + "冬眠2023,DJ阿智,新专辑,资料库,Apple Music,,123\n").encode()
    )
    review = service.review_incremental_track(entry["id"])
    assert review["entry"]["snapshot_status"] == "unmatched"
    assert review["entry"]["verification_status"] == "absent"
    assert review["candidates"]
    key = review["candidates"][0]["track_key"]
    service.link_incremental_track(entry["id"], key)
    linked = service.list_incremental_tracks()[0]
    assert linked["match_reason"] == "manual_link"
    assert linked["matched_track"]["title"] == "冬眠2023"
    assert linked["title"] == entry["title"]
    assert linked["snapshot_status"] == "matched"

    service = DualLibraryService(tmp_path / "musicflow.db")
    second, _ = service.import_snapshot(
        "second.csv", (CSV_HEADER + "冬眠2023 (新版名称),DJ阿智,新专辑,收藏,Apple Music,,123\n另一首,其他歌手,,收藏,Apple Music,,456\n").encode(), first["id"]
    )
    assert service.list_incremental_tracks()[0]["snapshot_status"] == "matched"
    assert service.list_incremental_tracks()[0]["match_reason"] == "manual_link"
    assert service.list_incremental_tracks()[0]["matched_track"]["title"] == "冬眠2023 (新版名称)"
    service.import_snapshot(
        "third.csv", (CSV_HEADER + "另一首,其他歌手,,收藏,Apple Music,,456\n").encode(), second["id"]
    )
    assert service.list_incremental_tracks()[0]["snapshot_status"] == "unmatched"
    with pytest.raises(ValueError, match="当前快照"):
        service.link_incremental_track(entry["id"], key)
    assert not service.review_incremental_track(entry["id"], "不存在的曲目")["candidates"]
    with pytest.raises(ValueError, match="不存在"):
        service.link_incremental_track("missing", key)


def test_incremental_review_separates_snapshot_and_manual_evidence(tmp_path: Path) -> None:
    """没有快照时不伪装为快照确认，关联支持撤销并保留人工确认。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track({"title": "记录名", "artist": "歌手"}, "manual")
    assert service.list_incremental_tracks()[0]["snapshot_status"] == "no_snapshot"
    assert service.review_incremental_track(entry["id"])["candidates"] == []
    service.confirm_incremental_track(entry["id"])
    service.import_snapshot("new.csv", (CSV_HEADER + "快照名,歌手,专辑,资料库,Apple Music,,123\n").encode())
    review = service.review_incremental_track(entry["id"], "快照名")
    assert len(review["candidates"]) == 1
    service.link_incremental_track(entry["id"], review["candidates"][0]["track_key"])
    service.link_incremental_track(entry["id"], None)
    result = service.list_incremental_tracks()[0]
    assert result["snapshot_status"] == "unmatched"
    assert result["verification_status"] == "manual_confirmed"


def test_snapshot_confirmed_entry_can_keep_independent_manual_evidence(tmp_path: Path) -> None:
    """已匹配快照的记录也能补充人工确认，快照更新后人工依据仍有效。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track({"apple_id": "123", "title": "歌曲", "artist": "歌手"}, "catalog")
    first, _ = service.import_snapshot("first.csv", (CSV_HEADER + "歌曲,歌手,,资料库,Apple Music,,123\n").encode())
    confirmed = service.confirm_incremental_track(entry["id"])
    assert confirmed["verification_status"] == "confirmed"
    assert confirmed["manual_confirmed_at"]
    service.import_snapshot("second.csv", (CSV_HEADER + "另一首,其他歌手,,资料库,Apple Music,,456\n").encode(), first["id"])
    assert service.list_incremental_tracks()[0]["verification_status"] == "manual_confirmed"


def test_snapshot_link_does_not_follow_ambiguous_apple_id(tmp_path: Path) -> None:
    """关联目标消失且同一 Apple ID 出现多版本时，不猜测原关联指向。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track({"title": "记录原名", "artist": "原歌手"}, "manual")
    first, _ = service.import_snapshot("first.csv", (CSV_HEADER + "歌曲,歌手,,资料库,Apple Music,,123\n").encode())
    key = service.review_incremental_track(entry["id"], "歌曲")["candidates"][0]["track_key"]
    service.link_incremental_track(entry["id"], key)
    service.import_snapshot("second.csv", (CSV_HEADER + "歌曲(现场),歌手,,资料库,Apple Music,,123\n歌曲(录音室),歌手,,资料库,Apple Music,,123\n").encode(), first["id"])
    assert service.list_incremental_tracks()[0]["snapshot_status"] == "unmatched"


def test_update_can_reuse_an_older_snapshot_csv(tmp_path: Path) -> None:
    """历史 CSV 内容已存在时，仍能用它更新当前快照。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    a_csv = (CSV_HEADER + "旧歌曲,歌手,旧专辑,资料库,Apple Music,,100\n").encode()
    b_csv = (CSV_HEADER + "新歌曲,歌手,新专辑,资料库,Apple Music,,200\n").encode()
    first, _ = service.import_snapshot("a.csv", a_csv)
    second, _ = service.import_snapshot("b.csv", b_csv)

    updated, created = service.import_snapshot("a.csv", a_csv, second["id"])

    assert created is True
    assert updated["id"] not in {first["id"], second["id"]}
    assert service.get_latest_snapshot()["id"] == updated["id"]


def test_listing_corrects_confirmation_left_by_an_older_version(tmp_path: Path) -> None:
    """旧版本遗留的快照确认在读取时按当前快照重新核对。"""
    service = DualLibraryService(tmp_path / "musicflow.db")
    entry = service.upsert_incremental_track(
        {"apple_id": "100", "title": "旧歌曲", "artist": "歌手", "album": "旧专辑"}, "catalog"
    )
    service.import_snapshot(
        "b.csv", (CSV_HEADER + "新歌曲,歌手,新专辑,资料库,Apple Music,,200\n").encode()
    )
    with service._connect() as connection:
        connection.execute(
            "UPDATE apple_incremental_entries SET verification_status = 'confirmed' WHERE id = ?",
            (entry["id"],),
        )

    assert service.list_incremental_tracks()[0]["verification_status"] == "absent"


def test_import_snapshot_deduplicates_same_track_from_multiple_playlists(tmp_path: Path) -> None:
    """同一曲目出现在多个歌单时，快照只保留一条曲目记录。"""
    service = create_service(tmp_path)
    content = (
        CSV_HEADER
        + "重复歌曲,歌手,专辑,歌单一,Favorite,CNABC1234567,1001\n"
        + "重复歌曲,歌手,专辑,歌单二,Favorite,CNABC1234567,1001\n"
        + "另一首,歌手,专辑,歌单二,Favorite,,1002\n"
    ).encode("utf-8")

    snapshot, created = service.import_snapshot("library.csv", content)

    assert created is True
    assert snapshot["row_count"] == 2
    assert snapshot["catalog_count"] == 2
    with service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM apple_snapshot_rows").fetchone()[0] == 2

    reordered_playlists = (
        CSV_HEADER
        + "重复歌曲,歌手,专辑,另一个歌单,Favorite,CNABC1234567,1001\n"
        + "另一首,歌手,专辑,歌单三,Favorite,,1002\n"
    ).encode("utf-8")
    repeated, repeated_created = service.import_snapshot("reordered.csv", reordered_playlists)
    assert repeated_created is False
    assert repeated["id"] == snapshot["id"]


def test_delete_snapshot_removes_its_tracks_and_match_decisions(tmp_path: Path) -> None:
    """删除 CSV 快照不影响本地文件，但要清理仅属于该快照的记录。"""
    service = create_service(tmp_path)
    snapshot, _ = service.import_snapshot(
        "library.csv",
        (CSV_HEADER + "歌曲,歌手,专辑,歌单,Favorite,,1001\n").encode("utf-8"),
    )
    result = service.reconcile([
        {"id": "local", "filename": "a.flac", "title": "歌曲", "artist": "其他歌手", "album": "专辑", "path": "/music/a.flac"},
    ])
    review = next(entry for entry in result["entries"] if entry["status"] == "review")
    service.save_match_decision("local", review["apple"]["track_key"], "confirmed")

    service.delete_snapshot(snapshot["id"])

    assert service.get_latest_snapshot() is None
    with service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM apple_tracks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM library_matches").fetchone()[0] == 0


def test_new_snapshot_marks_missing_tracks_as_possibly_removed(tmp_path: Path) -> None:
    """新快照缺失的历史曲目应保留并标记，而不是被删除。"""
    service = create_service(tmp_path)
    first = (CSV_HEADER + "旧歌曲,歌手,专辑,Library Songs,Favorite,,i.old\n").encode("utf-8")
    second = (CSV_HEADER + "新歌曲,歌手,专辑,Library Songs,Favorite,,i.new\n").encode("utf-8")

    service.import_snapshot("first.csv", first)
    service.import_snapshot("second.csv", second)

    with service._connect() as connection:
        states = dict(connection.execute("SELECT apple_id, presence_state FROM apple_tracks").fetchall())
    assert states == {"i.old": "possibly_removed", "i.new": "present"}


def test_reconcile_uses_isrc_metadata_and_manual_decision(tmp_path: Path) -> None:
    """专辑不同自动匹配，歌手不同的同名曲目必须人工确认。"""
    service = create_service(tmp_path)
    content = (
        CSV_HEADER
        + "ISRC歌曲,歌手甲,专辑甲,Library Songs,Favorite,CNABC1234567,1001\n"
        + "元数据歌曲,歌手乙,专辑乙,Library Songs,Favorite,,i.meta\n"
        + "专辑不同歌曲,歌手丙,Apple专辑,Library Songs,Favorite,,1003\n"
        + "同名待确认,G.E.M.邓紫棋,Apple专辑,Library Songs,Favorite,,1005\n"
        + "Apple独有,歌手丁,专辑丁,Library Songs,Favorite,,1004\n"
    ).encode("utf-8")
    service.import_snapshot("library.csv", content)
    local_tracks = [
        {"id": "local-isrc", "filename": "任意名称.flac", "title": "不同名字", "artist": "其他", "album": "其他", "isrc": "cnabc1234567", "path": "/music/a.flac"},
        {"id": "local-meta", "filename": "b.flac", "title": " 元数据歌曲 ", "artist": "歌手乙", "album": "专辑乙", "path": "/music/b.flac"},
        {"id": "local-album-diff", "filename": "c.flac", "title": "专辑不同歌曲", "artist": "歌手丙", "album": "本地专辑", "path": "/music/c.flac"},
        {"id": "local-review", "filename": "d.flac", "title": "同名待确认", "artist": "邓紫棋", "album": "本地专辑", "path": "/music/d.flac"},
        {"id": "local-only", "filename": "d.flac", "title": "本地独有", "artist": "歌手戊", "album": "专辑戊", "path": "/music/d.flac"},
    ]

    result = service.reconcile(local_tracks)

    assert result["summary"] == {"both": 3, "nas_only": 1, "apple_only": 1, "review": 1}
    reasons = {entry["match_reason"] for entry in result["entries"] if entry["status"] == "both"}
    assert reasons == {"isrc", "metadata_exact", "title_artist_album_diff"}
    review = next(entry for entry in result["entries"] if entry["status"] == "review")
    assert review["candidates"][0]["id"] == "local-review"

    service.save_match_decision("local-review", review["apple"]["track_key"], "confirmed")
    restarted_service = create_service(tmp_path)
    confirmed = restarted_service.reconcile(local_tracks)

    assert confirmed["summary"] == {"both": 4, "nas_only": 1, "apple_only": 1, "review": 0}
    assert any(entry["match_reason"] == "manual_confirmed" for entry in confirmed["entries"])


def test_reconcile_offers_same_title_with_different_artist_for_review(tmp_path: Path) -> None:
    """同名不同歌手可能是翻唱，只能交由人工确认。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (CSV_HEADER + "同名歌曲,Apple歌手,专辑,Library Songs,Favorite,,1001\n").encode("utf-8"),
    )

    result = service.reconcile([
        {"id": "local", "filename": "a.flac", "title": "同名歌曲", "artist": "飞牛歌手", "album": "专辑", "path": "/music/a.flac"},
    ])

    assert result["summary"] == {"both": 0, "nas_only": 0, "apple_only": 0, "review": 1}
    assert result["entries"][0]["match_reason"] == "title_cover_review"
    service.save_match_decision("local", result["entries"][0]["apple"]["track_key"], "confirmed")
    assert service.reconcile([{"id": "local", "title": "同名歌曲", "artist": "飞牛歌手"}])["summary"]["both"] == 1


def test_reconcile_keeps_fuzzy_title_candidates_for_manual_review(tmp_path: Path) -> None:
    """近似歌名只提供候选，不得自动合并。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (CSV_HEADER + "夜曲（现场版）,歌手,专辑,Library Songs,Favorite,,1001\n").encode("utf-8"),
    )

    result = service.reconcile([
        {"id": "local-fuzzy", "filename": "夜曲.flac", "title": "夜曲", "artist": "歌手", "album": "其他专辑", "path": "/music/a.flac"},
    ])

    review = next(entry for entry in result["entries"] if entry["status"] == "review")
    assert review["match_reason"] == "title_subject_artist_compatible"
    assert review["candidates"][0]["id"] == "local-fuzzy"


def test_reconcile_keeps_apple_title_descriptions_for_manual_confirmation(tmp_path: Path) -> None:
    """影视说明不同但歌名主体、艺名相符时必须人工确认。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (
            CSV_HEADER
            + "光年之外 (电影《太空旅客》主题曲),邓紫棋,Apple专辑,Library Songs,Favorite,,1001\n"
        ).encode("utf-8"),
    )

    result = service.reconcile([
        {"id": "local", "filename": "光年之外.flac", "title": "光年之外", "artist": "G.E.M.邓紫棋", "album": "本地专辑", "path": "/music/a.flac"},
    ])

    assert result["summary"] == {"both": 0, "nas_only": 0, "apple_only": 0, "review": 1}
    review = result["entries"][0]
    assert review["match_reason"] == "title_subject_artist_compatible"
    assert review["candidates"][0]["id"] == "local"


def test_reconcile_does_not_offer_unrelated_live_titles(tmp_path: Path) -> None:
    """相近歌名但歌手不相符时不能制造待确认候选。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (CSV_HEADER + "房间 (Live),刘瑞琦,专辑,Library Songs,Favorite,,1001\n").encode("utf-8"),
    )

    result = service.reconcile([
        {"id": "local", "filename": "攀登 (Live).flac", "title": "攀登 (Live)", "artist": "G.E.M.邓紫棋", "album": "专辑", "path": "/music/a.flac"},
    ])

    assert result["summary"] == {"both": 0, "nas_only": 1, "apple_only": 1, "review": 0}


def test_manual_incremental_entry_appears_in_reconciliation_and_keeps_decision(tmp_path: Path) -> None:
    """手动确认的新增 Apple 曲目应进入对账，人工决策应可保存。"""
    service = create_service(tmp_path)
    snapshot, _ = service.import_snapshot(
        "library.csv", (CSV_HEADER + "其他歌曲,其他歌手,专辑,Library Songs,Favorite,,1001\n").encode("utf-8"),
    )
    entry = service.upsert_incremental_track(
        {"title": "甲乙丙丁 (你我怎么两清)", "artist": "李佳薇", "album": "甲乙丙丁"}, "manual",
    )
    service.confirm_incremental_track(entry["id"])
    local = [{"id": "local", "filename": "a.flac", "title": "甲乙丙丁 (你我怎么两清)",
              "artist": "李佳薇", "album": "甲乙丙丁", "path": "/music/a.flac"}]
    result = service.reconcile(local)
    assert result["summary"]["both"] == 1
    assert next(row for row in result["entries"] if row["local"] and row["local"]["id"] == "local")["apple"]["apple_kind"] == "manual"
    service.save_match_decision("local", f"incremental:{entry['id']}", "confirmed")
    service.delete_snapshot(snapshot["id"])
    with service._connect() as connection:
        assert connection.execute("SELECT decision FROM library_matches WHERE apple_track_key = ?",
                                  (f"incremental:{entry['id']}",)).fetchone()[0] == "confirmed"


def test_manual_incremental_entry_does_not_duplicate_snapshot_track(tmp_path: Path) -> None:
    """快照已有同一首歌时，手动确认记录不应让对账数量重复。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER + "默,那英,默 - Single,Library Songs,Favorite,,1001\n"
    ).encode("utf-8"))
    entry = service.upsert_incremental_track({"title": "默", "artist": "那英", "album": "默 - Single"}, "manual")
    service.confirm_incremental_track(entry["id"])
    result = service.reconcile([{"id": "local", "filename": "a.flac", "title": "默", "artist": "那英",
                                "album": "默 - Single", "path": "/music/a.flac"}])
    assert result["summary"] == {"both": 1, "nas_only": 0, "apple_only": 0, "review": 0}


def test_reconcile_offers_version_and_credit_variants_for_review(tmp_path: Path) -> None:
    """现场版、合作歌手和跨字段署名只产生待确认候选。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER
        + "そばにいるね (feat. SoulJa),青山テルマ feat. SoulJa,专辑,Library Songs,Favorite,,1001\n"
        + "海阔天空 (Introduced by Beyond) [Live],Beyond,专辑,Library Songs,Favorite,,1002\n"
        + "GBL女神殿 - goddess temple,Dungeon and Fighter,BGM,Library Songs,Favorite,,1003\n"
    ).encode("utf-8"))
    local = [
        {"id": "japanese", "filename": "j.flac", "title": "そばにいるね", "artist": "青山テルマ, SoulJa", "album": "本地", "path": "/music/j.flac"},
        {"id": "live", "filename": "l.flac", "title": "海阔天空", "artist": "Beyond", "album": "本地", "path": "/music/l.flac"},
        {"id": "game", "filename": "g.flac", "title": "GBL女神殿", "artist": "DNF 地下城与勇士", "album": "Dungeon and Fighter", "path": "/music/g.flac"},
    ]
    result = service.reconcile(local)
    assert result["summary"] == {"both": 0, "nas_only": 0, "apple_only": 0, "review": 3}
    assert {row["candidates"][0]["id"] for row in result["entries"]} == {"japanese", "live", "game"}


def test_reconcile_offers_artist_album_and_alias_variants_for_review(tmp_path: Path) -> None:
    """同名曲的合作歌手顺序、专辑和常见艺名差异只生成待确认候选。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER
        + "New Soul,Yael Naïm,Yael Naim,Library Songs,Favorite,,1001\n"
        + "My Heart,Different Heaven & Eh!de,My Heart - Single,Library Songs,Favorite,,1002\n"
        + "MY ALL,滨崎步,GUILTY,Library Songs,Favorite,,1003\n"
        + "SAKURA,生物股长,桜咲く街物語,Library Songs,Favorite,,1004\n"
        + "ピースサイン - Peace Sign,米津玄师,BOOTLEG,Library Songs,Favorite,,1005\n"
    ).encode("utf-8"))
    local = [
        {"id": "new-soul", "filename": "1.flac", "title": "New Soul", "artist": "Yael Naim", "album": "Yael Naim", "path": "/music/1.flac"},
        {"id": "my-heart", "filename": "2.flac", "title": "My Heart", "artist": "EH!DE、Different Heaven", "album": "My Heart", "path": "/music/2.flac"},
        {"id": "my-all", "filename": "3.flac", "title": "MY ALL", "artist": "浜崎あゆみ", "album": "GUILTY", "path": "/music/3.flac"},
        {"id": "sakura", "filename": "4.flac", "title": "SAKURA", "artist": "いきものがかり", "album": "SAKURA", "path": "/music/4.flac"},
        {"id": "peace", "filename": "5.flac", "title": "ピースサイン", "artist": "米津玄師", "album": "ピースサイン", "path": "/music/5.flac"},
    ]
    result = service.reconcile(local)
    assert result["summary"] == {"both": 0, "nas_only": 0, "apple_only": 0, "review": 5}
    assert {row["candidates"][0]["id"] for row in result["entries"]} == {track["id"] for track in local}


def test_reconcile_keeps_same_title_and_generic_album_as_manual_candidate(tmp_path: Path) -> None:
    """同名与普通专辑名不能自动合并，但可以展示翻唱候选。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER + "同名歌曲,歌手甲,专辑,Library Songs,Favorite,,1001\n"
    ).encode("utf-8"))
    result = service.reconcile([{"id": "local", "filename": "a.flac", "title": "同名歌曲",
                                "artist": "歌手乙", "album": "专辑", "path": "/music/a.flac"}])
    assert result["summary"] == {"both": 0, "nas_only": 0, "apple_only": 0, "review": 1}
    assert result["entries"][0]["match_reason"] == "title_cover_review"


def test_reconcile_reviews_local_title_with_artist_prefix(tmp_path: Path) -> None:
    """本地文件把歌手写进歌名时，保留为待确认。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER + "50 Ways to Say Goodbye,Train,专辑,Library Songs,Favorite,,1001\n"
    ).encode("utf-8"))
    result = service.reconcile([{"id": "local", "title": "Train - 50 Ways to Say Goodbye",
                                "artist": "", "album": "专辑"}])
    assert result["summary"]["review"] == 1
    assert result["entries"][0]["candidates"][0]["id"] == "local"


def test_reconcile_reviews_parenthesized_title_segment(tmp_path: Path) -> None:
    """歌名一侧把上集放在括号中，也应进入人工候选。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER + "爱的故事(上集),孙耀威,专辑,Library Songs,Favorite,,1001\n"
    ).encode("utf-8"))
    result = service.reconcile([{"id": "local", "title": "爱的故事上集 (BB鼓版)",
                                "artist": "诗南", "album": "专辑"}])
    assert result["summary"]["review"] == 1


def test_reconcile_keeps_user_rejected_name_similarities_separate(tmp_path: Path) -> None:
    """用户排除的五组近似名称不能自动匹配或进入待确认。"""
    service = create_service(tmp_path)
    apple_tracks = [
        ("Booty Music 2 (feat. Ace Hood)", "Git Fresh"),
        ("Seve (Radio Edit)", "Tez Cadey"),
        ("Loner", "CNBLUE"),
        ("这,就是爱 (Live)", "张杰"),
    ]
    local_tracks = [
        ("Booty Music", "Deep Side"),
        ("Seven (Jiaye Reboot)", "Jiaye、Tobu"),
        ("SEVEN", "蔡依林"),
        ("Alone", "Alan Walker"),
        ("就是爱你", "陶喆"),
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("Track name", "Artist name", "Album", "Playlist name", "Type", "ISRC", "Apple - id"))
    for index, (title, artist) in enumerate(apple_tracks, 1):
        writer.writerow((title, artist, "专辑", "Library Songs", "Favorite", "", str(index)))
    service.import_snapshot("library.csv", output.getvalue().encode("utf-8"))
    result = service.reconcile([
        {"id": str(index), "title": title, "artist": artist, "album": "专辑"}
        for index, (title, artist) in enumerate(local_tracks, 1)
    ])
    assert result["summary"] == {"both": 0, "nas_only": 5, "apple_only": 4, "review": 0}


def test_apple_precheck_includes_pending_incremental_record(tmp_path: Path) -> None:
    """已记录待确认的 Apple Music 曲目也应阻止静默重复上传。"""
    service = create_service(tmp_path)
    service.upsert_incremental_track({"title": "翻唱歌曲", "artist": "歌手甲", "album": "专辑"}, "catalog")
    candidates = service.find_apple_candidates({"title": "翻唱歌曲", "artist": "歌手乙"})
    assert len(candidates) == 1
    assert candidates[0]["verification_status"] == "pending"


def test_reconcile_offers_artist_alias_with_guest_and_version_for_review(tmp_path: Path) -> None:
    """艺名别称及合作歌手、重制版本只能列为候选，优先展示标题完全相同的版本。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER
        + "βios (feat. Mika Kobayashi),泽野弘之,原声带,Library Songs,Favorite,,1001\n"
        + "Beautiful World (PLANiTb Acoustica Mix) [2021 Remastered],Utada,Single,Library Songs,Favorite,,1002\n"
        + "unravel (acoustic version),TK from Ling tosite sigure,Signal - Single,Library Songs,Favorite,,1003\n"
    ).encode("utf-8"))
    local = [
        {"id": "bios", "filename": "1.flac", "title": "βios (feat.Mika Kobayashi)", "artist": "澤野弘之、小林未郁", "album": "其他", "path": "/music/1.flac"},
        {"id": "beautiful", "filename": "2.flac", "title": "Beautiful World", "artist": "宇多田ヒカル", "album": "其他", "path": "/music/2.flac"},
        {"id": "acoustic", "filename": "3.flac", "title": "unravel (acoustic version)", "artist": "TK from 凛として時雨", "album": "Signal", "path": "/music/3.flac"},
        {"id": "plain", "filename": "4.flac", "title": "unravel", "artist": "TK from 凛冽时雨", "album": "其他", "path": "/music/4.flac"},
    ]
    result = service.reconcile(local)
    assert result["summary"] == {"both": 0, "nas_only": 1, "apple_only": 0, "review": 3}
    reviews = {row["apple"]["title"]: row for row in result["entries"] if row["status"] == "review"}
    assert reviews["unravel (acoustic version)"]["candidates"][0]["id"] == "acoustic"
    assert len(reviews["unravel (acoustic version)"]["candidates"]) == 1


def test_reconcile_offers_translated_artist_and_long_shared_title_for_review(tmp_path: Path) -> None:
    """多语言团名和较长的同歌手标题主体可待确认，短标题前缀不应误判。"""
    service = create_service(tmp_path)
    service.import_snapshot("library.csv", (
        CSV_HEADER
        + "Nobody (Korean Ver.),奇迹女孩,WONDER GIRLS,Library Songs,Favorite,,1001\n"
        + "Never Say Goodbye,베이비 복스 2기,五. 歌. 舞. 世. 炅,Library Songs,Favorite,,1002\n"
        + "世界が終るまでは… [WANDS 第5期 ver.],WANDS,Single,Library Songs,Favorite,,1003\n"
        + '"Alone, Pt. II",Alan Walker,Alone,Library Songs,Favorite,,1004\n'
    ).encode("utf-8"))
    local = [
        {"id": "nobody", "filename": "1.flac", "title": "Nobody", "artist": "Wonder Girls", "album": "其他", "path": "/music/1.flac"},
        {"id": "goodbye", "filename": "2.flac", "title": "Never Say Goodbye", "artist": "Baby V.O.X", "album": "其他", "path": "/music/2.flac"},
        {"id": "wands", "filename": "3.flac", "title": "世界が終るまでは…~TV Version~", "artist": "WANDS", "album": "其他", "path": "/music/3.flac"},
        {"id": "alone", "filename": "4.flac", "title": "Alone", "artist": "Alan Walker", "album": "其他", "path": "/music/4.flac"},
    ]
    result = service.reconcile(local)
    reviews = [row for row in result["entries"] if row["status"] == "review"]
    assert {row["candidates"][0]["id"] for row in reviews} == {"nobody", "goodbye", "wands"}
    assert result["summary"] == {"both": 0, "nas_only": 1, "apple_only": 1, "review": 3}


def test_save_match_decisions_saves_batch_atomically(tmp_path: Path) -> None:
    """批量确认应一次写入所有人工决策。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (CSV_HEADER
         + "同名一,Apple歌手,专辑,Library Songs,Favorite,,1001\n"
         + "同名二,Apple歌手,专辑,Library Songs,Favorite,,1002\n").encode("utf-8"),
    )
    result = service.reconcile([
        {"id": "local-1", "filename": "a.flac", "title": "同名一", "artist": "G.E.M.Apple歌手", "album": "本地专辑", "path": "/music/a.flac"},
        {"id": "local-2", "filename": "b.flac", "title": "同名二", "artist": "G.E.M.Apple歌手", "album": "本地专辑", "path": "/music/b.flac"},
    ])
    reviews = [entry for entry in result["entries"] if entry["status"] == "review"]

    service.save_match_decisions([
        ("local-1", reviews[0]["apple"]["track_key"], "confirmed"),
        ("local-2", reviews[1]["apple"]["track_key"], "confirmed"),
    ])

    confirmed = service.reconcile([
        {"id": "local-1", "filename": "a.flac", "title": "同名一", "artist": "G.E.M.Apple歌手", "album": "本地专辑", "path": "/music/a.flac"},
        {"id": "local-2", "filename": "b.flac", "title": "同名二", "artist": "G.E.M.Apple歌手", "album": "本地专辑", "path": "/music/b.flac"},
    ])
    assert confirmed["summary"]["both"] == 2


def test_normalize_text_only_applies_safe_exact_normalization() -> None:
    """标准化只统一大小写、宽度和标点，不做翻译或拼音推断。"""
    assert normalize_text("ＡＢＣ - 测试 歌曲") == "abc测试歌曲"
