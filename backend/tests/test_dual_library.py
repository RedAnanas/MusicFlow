from pathlib import Path

from app.services.dual_library_service import DualLibraryService, normalize_text


CSV_HEADER = "Track name,Artist name,Album,Playlist name,Type,ISRC,Apple - id\n"


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
        "手动曲目": "absent", "自动曲目": "absent"
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


def test_reconcile_does_not_offer_same_title_with_unrelated_artist(tmp_path: Path) -> None:
    """同名但歌手完全不同应分别保留为单库曲目。"""
    service = create_service(tmp_path)
    service.import_snapshot(
        "library.csv",
        (CSV_HEADER + "同名歌曲,Apple歌手,专辑,Library Songs,Favorite,,1001\n").encode("utf-8"),
    )

    result = service.reconcile([
        {"id": "local", "filename": "a.flac", "title": "同名歌曲", "artist": "飞牛歌手", "album": "专辑", "path": "/music/a.flac"},
    ])

    assert result["summary"] == {"both": 0, "nas_only": 1, "apple_only": 1, "review": 0}


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
