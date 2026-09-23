import csv
import difflib
import hashlib
import io
import json
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from app.config import settings


REQUIRED_COLUMNS = (
    "Track name",
    "Artist name",
    "Album",
    "Playlist name",
    "Type",
    "ISRC",
    "Apple - id",
)


def normalize_text(value: Optional[str]) -> str:
    """生成用于精确匹配的稳定文本，不执行可能误判的模糊转换。"""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(character for character in normalized if character.isalnum())


def normalize_title_subject(value: Optional[str]) -> str:
    """提取用于人工候选的歌名主体，保留原始歌名用于展示和自动匹配。"""
    title = (value or "").strip()
    # Apple Music 常将影视说明、现场等附在歌名末尾；这类版本差异只能作为人工候选。
    while True:
        stripped = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", title).strip()
        if stripped == title:
            return normalize_text(title)
        title = stripped


class DualLibraryService:
    """持久化 Apple Music 快照、曲目和双库匹配决策。"""

    def __init__(self, database_path: Optional[Path] = None):
        self.database_path = database_path or Path(settings.DATA_DIR) / "musicflow.db"

    @contextmanager
    def _connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS apple_library_snapshots (
                    id TEXT PRIMARY KEY,
                    imported_at TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL UNIQUE,
                    row_count INTEGER NOT NULL,
                    catalog_count INTEGER NOT NULL,
                    uploaded_count INTEGER NOT NULL,
                    unknown_count INTEGER NOT NULL,
                    isrc_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS apple_tracks (
                    track_key TEXT PRIMARY KEY,
                    apple_id TEXT NOT NULL,
                    apple_kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT NOT NULL,
                    isrc TEXT,
                    normalized_title TEXT NOT NULL,
                    normalized_artist TEXT NOT NULL,
                    normalized_album TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    presence_state TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_apple_tracks_isrc ON apple_tracks(isrc);
                CREATE INDEX IF NOT EXISTS idx_apple_tracks_metadata
                    ON apple_tracks(normalized_title, normalized_artist, normalized_album);

                CREATE TABLE IF NOT EXISTS apple_snapshot_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT NOT NULL REFERENCES apple_library_snapshots(id) ON DELETE CASCADE,
                    row_index INTEGER NOT NULL,
                    track_key TEXT NOT NULL REFERENCES apple_tracks(track_key),
                    playlist_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    UNIQUE(snapshot_id, row_index)
                );

                CREATE INDEX IF NOT EXISTS idx_snapshot_rows_snapshot
                    ON apple_snapshot_rows(snapshot_id);

                CREATE TABLE IF NOT EXISTS library_matches (
                    local_file_id TEXT NOT NULL,
                    apple_track_key TEXT NOT NULL REFERENCES apple_tracks(track_key),
                    decision TEXT NOT NULL CHECK(decision IN ('confirmed', 'rejected')),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(local_file_id, apple_track_key)
                );

                CREATE TABLE IF NOT EXISTS reconciliation_results (
                    snapshot_id TEXT NOT NULL,
                    local_index_version INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id, local_index_version)
                );

                CREATE TABLE IF NOT EXISTS apple_incremental_entries (
                    id TEXT PRIMARY KEY,
                    identity_key TEXT NOT NULL UNIQUE,
                    apple_id TEXT,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT NOT NULL,
                    isrc TEXT,
                    normalized_title TEXT NOT NULL,
                    normalized_artist TEXT NOT NULL,
                    normalized_album TEXT NOT NULL,
                    source TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    acquisition_job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_apple_incremental_isrc
                    ON apple_incremental_entries(isrc);
                CREATE INDEX IF NOT EXISTS idx_apple_incremental_metadata
                    ON apple_incremental_entries(normalized_title, normalized_artist, normalized_album);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(apple_incremental_entries)")}
            if "manual_confirmed_at" not in columns:
                connection.execute("ALTER TABLE apple_incremental_entries ADD COLUMN manual_confirmed_at TEXT")
                connection.execute(
                    "UPDATE apple_incremental_entries SET manual_confirmed_at = confirmed_at WHERE verification_status = 'manual_confirmed'"
                )

    def get_cached_reconciliation(self, snapshot_id: str, local_index_version: int) -> Optional[dict]:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT result_json FROM reconciliation_results
                WHERE snapshot_id = ? AND local_index_version = ?
                """,
                (snapshot_id, local_index_version),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def save_cached_reconciliation(self, snapshot_id: str, local_index_version: int, result: dict) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO reconciliation_results(
                    snapshot_id, local_index_version, result_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    local_index_version,
                    json.dumps(result, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def clear_reconciliation_cache(self) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM reconciliation_results")

    @staticmethod
    def _decode_csv(content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV 必须使用 UTF-8 编码") from exc

    @staticmethod
    def _classify_apple_id(apple_id: str) -> str:
        if apple_id.startswith("i."):
            return "uploaded"
        if apple_id.isdigit():
            return "catalog"
        return "unknown"

    @staticmethod
    def _track_key(row: dict[str, str]) -> str:
        identity = json.dumps(
            {
                "apple_id": row["Apple - id"],
                "title": normalize_text(row["Track name"]),
                "artist": normalize_text(row["Artist name"]),
                "album": normalize_text(row["Album"]),
                "isrc": row["ISRC"].strip().upper(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def import_snapshot(self, filename: str, content: bytes, replace_snapshot_id: Optional[str] = None) -> tuple[dict, bool]:
        if not content:
            raise ValueError("CSV 文件为空")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("CSV 文件不能超过 10 MB")

        self.initialize()
        reader = csv.DictReader(io.StringIO(self._decode_csv(content)))
        fieldnames = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing:
            raise ValueError(f"CSV 缺少必要列：{', '.join(missing)}")

        rows = []
        seen_track_keys = set()
        for row_index, source_row in enumerate(reader, start=1):
            row = {column: (source_row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
            if not row["Track name"] or not row["Artist name"] or not row["Apple - id"]:
                raise ValueError(f"第 {row_index + 1} 行缺少歌名、歌手或 Apple ID")
            row["ISRC"] = row["ISRC"].upper()
            track_key = self._track_key(row)
            if track_key in seen_track_keys:
                continue
            seen_track_keys.add(track_key)
            rows.append((row_index, row, track_key, self._classify_apple_id(row["Apple - id"])))

        if not rows:
            raise ValueError("CSV 中没有曲目记录")

        # 快照身份只基于去重后的曲目集合，歌单归属变化不应产生新快照。
        source_sha256 = hashlib.sha256(
            "\n".join(sorted(track_key for _, _, track_key, _ in rows)).encode("utf-8")
        ).hexdigest()
        duplicate_snapshot_id = None
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM apple_library_snapshots WHERE source_sha256 = ?",
                (source_sha256,),
            ).fetchone()
            if existing:
                if replace_snapshot_id and existing["id"] != replace_snapshot_id:
                    duplicate_snapshot_id = existing["id"]
                elif replace_snapshot_id:
                    latest = connection.execute(
                        "SELECT id FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1"
                    ).fetchone()
                    if not latest or latest["id"] != replace_snapshot_id:
                        raise ValueError("当前快照已变化，请刷新后重试")
                    return dict(existing), False
                else:
                    return dict(existing), False

        snapshot_id = str(uuid.uuid4())
        imported_at = datetime.now(timezone.utc).isoformat()
        counts = {
            "catalog_count": sum(kind == "catalog" for _, _, _, kind in rows),
            "uploaded_count": sum(kind == "uploaded" for _, _, _, kind in rows),
            "unknown_count": sum(kind == "unknown" for _, _, _, kind in rows),
            "isrc_count": sum(bool(row["ISRC"]) for _, row, _, _ in rows),
        }

        with self._connect() as connection:
            if replace_snapshot_id:
                latest = connection.execute(
                    "SELECT id FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1"
                ).fetchone()
                if not latest or latest["id"] != replace_snapshot_id:
                    raise ValueError("当前快照已变化，请刷新后重试")
                if duplicate_snapshot_id:
                    self._delete_snapshot_in_connection(connection, duplicate_snapshot_id)
            connection.execute(
                """
                INSERT INTO apple_library_snapshots (
                    id, imported_at, source_filename, source_sha256, row_count,
                    catalog_count, uploaded_count, unknown_count, isrc_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    imported_at,
                    Path(filename).name,
                    source_sha256,
                    len(rows),
                    counts["catalog_count"],
                    counts["uploaded_count"],
                    counts["unknown_count"],
                    counts["isrc_count"],
                ),
            )
            connection.execute("UPDATE apple_tracks SET presence_state = 'possibly_removed'")
            for row_index, row, track_key, apple_kind in rows:
                connection.execute(
                    """
                    INSERT INTO apple_tracks (
                        track_key, apple_id, apple_kind, title, artist, album, isrc,
                        normalized_title, normalized_artist, normalized_album,
                        first_seen_at, last_seen_at, presence_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'present')
                    ON CONFLICT(track_key) DO UPDATE SET
                        apple_id = excluded.apple_id,
                        apple_kind = excluded.apple_kind,
                        title = excluded.title,
                        artist = excluded.artist,
                        album = excluded.album,
                        isrc = excluded.isrc,
                        last_seen_at = excluded.last_seen_at,
                        presence_state = 'present'
                    """,
                    (
                        track_key,
                        row["Apple - id"],
                        apple_kind,
                        row["Track name"],
                        row["Artist name"],
                        row["Album"],
                        row["ISRC"] or None,
                        normalize_text(row["Track name"]),
                        normalize_text(row["Artist name"]),
                        normalize_text(row["Album"]),
                        imported_at,
                        imported_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO apple_snapshot_rows (
                        snapshot_id, row_index, track_key, playlist_name, source_type, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        row_index,
                        track_key,
                        row["Playlist name"],
                        row["Type"],
                        json.dumps(row, ensure_ascii=False),
                    ),
                )

            if replace_snapshot_id:
                self._delete_snapshot_in_connection(connection, replace_snapshot_id)
            self._sync_incremental_confirmations(connection)

        return self.get_snapshot(snapshot_id), True

    def get_snapshot(self, snapshot_id: str) -> dict:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM apple_library_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
        if not row:
            raise ValueError("Apple Music 快照不存在")
        return dict(row)

    def get_latest_snapshot(self) -> Optional[dict]:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def delete_snapshot(self, snapshot_id: str) -> None:
        """删除指定快照及其孤立曲目、人工匹配决策。"""
        self.initialize()
        with self._connect() as connection:
            self._delete_snapshot_in_connection(connection, snapshot_id)
            self._sync_incremental_confirmations(connection)

    @staticmethod
    def _delete_snapshot_in_connection(connection: sqlite3.Connection, snapshot_id: str) -> None:
        exists = connection.execute(
            "SELECT 1 FROM apple_library_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if not exists:
            raise ValueError("Apple Music 快照不存在")
        connection.execute("DELETE FROM apple_library_snapshots WHERE id = ?", (snapshot_id,))
        connection.execute(
            "DELETE FROM library_matches WHERE apple_track_key NOT IN (SELECT DISTINCT track_key FROM apple_snapshot_rows)"
        )
        connection.execute(
            "DELETE FROM apple_tracks WHERE track_key NOT IN (SELECT DISTINCT track_key FROM apple_snapshot_rows)"
        )

    @staticmethod
    def _sync_incremental_confirmations(connection: sqlite3.Connection) -> None:
        """只用当前快照标记 CSV 确认，并保留独立的手动确认。"""
        snapshot = connection.execute(
            "SELECT id, imported_at FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        tracks = connection.execute(
            """
            SELECT t.apple_id, t.isrc, t.normalized_title, t.normalized_artist, t.normalized_album
            FROM apple_snapshot_rows r JOIN apple_tracks t ON t.track_key = r.track_key
            WHERE r.snapshot_id = ?
            """,
            (snapshot["id"] if snapshot else "",),
        ).fetchall()
        apple_ids = {track["apple_id"] for track in tracks if track["apple_id"]}
        isrcs = {track["isrc"] for track in tracks if track["isrc"]}
        metadata = {
            (track["normalized_title"], track["normalized_artist"], track["normalized_album"])
            for track in tracks
        }
        now = datetime.now(timezone.utc).isoformat()
        for entry in connection.execute("SELECT * FROM apple_incremental_entries").fetchall():
            matched = (
                bool(entry["apple_id"] and entry["apple_id"] in apple_ids)
                or bool(entry["isrc"] and entry["isrc"] in isrcs)
                or (entry["normalized_title"], entry["normalized_artist"], entry["normalized_album"]) in metadata
            )
            if matched:
                status, confirmed_at = "confirmed", snapshot["imported_at"]
            elif snapshot and entry["manual_confirmed_at"] and entry["manual_confirmed_at"] > snapshot["imported_at"]:
                status, confirmed_at = "manual_confirmed", entry["manual_confirmed_at"]
            elif snapshot and entry["created_at"] <= snapshot["imported_at"]:
                status, confirmed_at = "absent", None
            else:
                status = "manual_confirmed" if entry["manual_confirmed_at"] else "pending"
                confirmed_at = entry["manual_confirmed_at"]
            if status != entry["verification_status"] or confirmed_at != entry["confirmed_at"]:
                connection.execute(
                    "UPDATE apple_incremental_entries SET verification_status = ?, confirmed_at = ?, updated_at = ? WHERE id = ?",
                    (status, confirmed_at, now, entry["id"]),
                )

    @staticmethod
    def _incremental_identity(track: dict) -> tuple[str, dict]:
        title = str(track.get("title") or track.get("song_name") or "").strip()
        artist = str(track.get("artist") or track.get("singers") or "").strip()
        album = str(track.get("album") or "").strip()
        apple_id = str(track.get("apple_id") or track.get("track_id") or "").strip()
        isrc = str(track.get("isrc") or "").strip().upper()
        if not title or not artist:
            raise ValueError("Apple Music 曲目必须包含歌名和歌手")
        normalized = {
            "title": normalize_text(title),
            "artist": normalize_text(artist),
            "album": normalize_text(album),
        }
        identity = apple_id or isrc or json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        identity_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return identity_key, {
            "apple_id": apple_id or None,
            "title": title,
            "artist": artist,
            "album": album,
            "isrc": isrc or None,
            "normalized_title": normalized["title"],
            "normalized_artist": normalized["artist"],
            "normalized_album": normalized["album"],
        }

    def upsert_incremental_track(
        self,
        track: dict,
        source: str,
        acquisition_job_id: Optional[str] = None,
    ) -> dict:
        """记录手动添加或交接中的 Apple Music 曲目，等待后续快照确认。"""
        if source not in {"manual", "catalog", "handoff"}:
            raise ValueError("Apple Music 增量来源无效")
        self.initialize()
        identity_key, values = self._incremental_identity(track)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO apple_incremental_entries (
                    id, identity_key, apple_id, title, artist, album, isrc,
                    normalized_title, normalized_artist, normalized_album,
                    source, verification_status, acquisition_job_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    apple_id = COALESCE(excluded.apple_id, apple_incremental_entries.apple_id),
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    isrc = COALESCE(excluded.isrc, apple_incremental_entries.isrc),
                    source = excluded.source,
                    verification_status = CASE WHEN apple_incremental_entries.verification_status = 'absent' THEN 'pending' ELSE apple_incremental_entries.verification_status END,
                    confirmed_at = CASE WHEN apple_incremental_entries.verification_status = 'absent' THEN NULL ELSE apple_incremental_entries.confirmed_at END,
                    created_at = CASE WHEN apple_incremental_entries.verification_status = 'absent' THEN excluded.created_at ELSE apple_incremental_entries.created_at END,
                    acquisition_job_id = COALESCE(excluded.acquisition_job_id, apple_incremental_entries.acquisition_job_id),
                    updated_at = excluded.updated_at
                """,
                (
                    uuid.uuid4().hex,
                    identity_key,
                    values["apple_id"],
                    values["title"],
                    values["artist"],
                    values["album"],
                    values["isrc"],
                    values["normalized_title"],
                    values["normalized_artist"],
                    values["normalized_album"],
                    source,
                    acquisition_job_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM apple_incremental_entries WHERE identity_key = ?",
                (identity_key,),
            ).fetchone()
        return dict(row)

    def list_incremental_tracks(self) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            self._sync_incremental_confirmations(connection)
            rows = connection.execute(
                "SELECT * FROM apple_incremental_entries ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def confirm_incremental_track(self, entry_id: str) -> dict:
        """将增量记录标记为人工确认，保留后续 CSV 确认的独立状态。"""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM apple_incremental_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Apple Music 增量记录不存在")
            if row["verification_status"] in {"pending", "absent"}:
                connection.execute(
                    "UPDATE apple_incremental_entries SET verification_status = 'manual_confirmed', confirmed_at = ?, manual_confirmed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, now, entry_id),
                )
            return dict(connection.execute(
                "SELECT * FROM apple_incremental_entries WHERE id = ?", (entry_id,)
            ).fetchone())

    def delete_incremental_track(self, entry_id: str) -> None:
        self.initialize()
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM apple_incremental_entries WHERE id = ?",
                (entry_id,),
            ).rowcount
        if not deleted:
            raise ValueError("Apple Music 增量记录不存在")

    def save_match_decision(self, local_file_id: str, apple_track_key: str, decision: str) -> None:
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("匹配决策必须是 confirmed 或 rejected")
        self.initialize()
        with self._connect() as connection:
            track = connection.execute(
                "SELECT 1 FROM apple_tracks WHERE track_key = ?",
                (apple_track_key,),
            ).fetchone()
            if not track:
                raise ValueError("Apple Music 曲目不存在")
            connection.execute(
                """
                INSERT INTO library_matches (local_file_id, apple_track_key, decision, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(local_file_id, apple_track_key) DO UPDATE SET
                    decision = excluded.decision,
                    updated_at = excluded.updated_at
                """,
                (local_file_id, apple_track_key, decision, datetime.now(timezone.utc).isoformat()),
            )

    def save_match_decisions(self, decisions: Iterable[tuple[str, str, str]]) -> None:
        """原子保存一批人工确认或排除决策。"""
        prepared = list(decisions)
        if not prepared:
            raise ValueError("至少选择一条匹配记录")
        if any(decision not in {"confirmed", "rejected"} for _, _, decision in prepared):
            raise ValueError("匹配决策必须是 confirmed 或 rejected")
        with self._connect() as connection:
            known_keys = {
                row[0]
                for row in connection.execute(
                    "SELECT track_key FROM apple_tracks WHERE track_key IN ({})".format(
                        ",".join("?" for _ in prepared)
                    ),
                    [apple_track_key for _, apple_track_key, _ in prepared],
                ).fetchall()
            }
            if any(apple_track_key not in known_keys for _, apple_track_key, _ in prepared):
                raise ValueError("Apple Music 曲目不存在")
            now = datetime.now(timezone.utc).isoformat()
            connection.executemany(
                """
                INSERT INTO library_matches (local_file_id, apple_track_key, decision, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(local_file_id, apple_track_key) DO UPDATE SET
                    decision = excluded.decision,
                    updated_at = excluded.updated_at
                """,
                [(local_file_id, apple_track_key, decision, now) for local_file_id, apple_track_key, decision in prepared],
            )

    def _latest_tracks(self, connection: sqlite3.Connection) -> list[dict]:
        latest = connection.execute(
            "SELECT id FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = connection.execute(
            """
            SELECT t.*, r.row_index
            FROM apple_snapshot_rows r
            JOIN apple_tracks t ON t.track_key = r.track_key
            WHERE r.snapshot_id = ?
            ORDER BY r.row_index
            """,
            (latest["id"],),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _prepare_local_tracks(local_tracks: Iterable[dict]) -> list[dict]:
        prepared = []
        for track in local_tracks:
            title = (track.get("title") or Path(track.get("filename") or "").stem).strip()
            artist = (track.get("artist") or "").strip()
            album = (track.get("album") or "").strip()
            prepared.append({
                **track,
                "title": title,
                "artist": artist,
                "album": album,
                "isrc": (track.get("isrc") or "").strip().upper() or None,
                "normalized_title": normalize_text(title),
                "normalized_title_subject": normalize_title_subject(title),
                "normalized_artist": normalize_text(artist),
                "normalized_album": normalize_text(album),
            })
        return prepared

    def reconcile(self, local_tracks: Iterable[dict]) -> dict:
        self.initialize()
        local = self._prepare_local_tracks(local_tracks)
        local_by_id = {track["id"]: track for track in local}
        with self._connect() as connection:
            apple_tracks = self._latest_tracks(connection)
            decisions = [dict(row) for row in connection.execute("SELECT * FROM library_matches").fetchall()]

        confirmed = {
            decision["apple_track_key"]: decision["local_file_id"]
            for decision in decisions if decision["decision"] == "confirmed"
        }
        rejected = {
            (decision["apple_track_key"], decision["local_file_id"])
            for decision in decisions if decision["decision"] == "rejected"
        }

        by_isrc: dict[str, list[dict]] = {}
        by_metadata: dict[tuple[str, str, str], list[dict]] = {}
        by_title_artist: dict[tuple[str, str], list[dict]] = {}
        by_title_subject: dict[str, list[dict]] = {}
        for track in local:
            if track["isrc"]:
                by_isrc.setdefault(track["isrc"], []).append(track)
            by_metadata.setdefault((track["normalized_title"], track["normalized_artist"], track["normalized_album"]), []).append(track)
            by_title_artist.setdefault((track["normalized_title"], track["normalized_artist"]), []).append(track)
            by_title_subject.setdefault(track["normalized_title_subject"], []).append(track)

        entries = []
        matched_local_ids = set()
        review_local_ids = set()
        for apple in apple_tracks:
            track_key = apple["track_key"]
            confirmed_local = local_by_id.get(confirmed.get(track_key, ""))
            if confirmed_local:
                matched_local_ids.add(confirmed_local["id"])
                entries.append(self._entry("both", apple, confirmed_local, "manual_confirmed", []))
                continue

            candidates: list[dict] = []
            reason = ""
            if apple["isrc"]:
                candidates = by_isrc.get(apple["isrc"], [])
                reason = "isrc"
            if not candidates:
                candidates = by_metadata.get((apple["normalized_title"], apple["normalized_artist"], apple["normalized_album"]), [])
                reason = "metadata_exact"
            candidates = [candidate for candidate in candidates if (track_key, candidate["id"]) not in rejected]
            if len(candidates) == 1:
                matched_local_ids.add(candidates[0]["id"])
                entries.append(self._entry("both", apple, candidates[0], reason, []))
                continue
            if not candidates:
                candidates = by_title_artist.get((apple["normalized_title"], apple["normalized_artist"]), [])
                candidates = [candidate for candidate in candidates if (track_key, candidate["id"]) not in rejected]
                reason = "title_artist_album_diff"
            if len(candidates) == 1:
                matched_local_ids.add(candidates[0]["id"])
                entries.append(self._entry("both", apple, candidates[0], reason, []))
                continue
            if not candidates:
                apple_title_subject = normalize_title_subject(apple["title"])
                same_title = by_title_subject.get(apple_title_subject, [])
                candidates = [
                    candidate for candidate in same_title
                    if (track_key, candidate["id"]) not in rejected
                    and self._artists_are_compatible(apple["normalized_artist"], candidate["normalized_artist"])
                ]
                reason = "title_subject_artist_compatible"
            if not candidates:
                candidates = self._fuzzy_candidates(apple, local, rejected)
                reason = "fuzzy"
            if candidates:
                review_local_ids.update(candidate["id"] for candidate in candidates)
                entries.append(self._entry("review", apple, None, reason, candidates))
            else:
                entries.append(self._entry("apple_only", apple, None, "no_match", []))

        for track in local:
            if track["id"] not in matched_local_ids and track["id"] not in review_local_ids:
                entries.append(self._entry("nas_only", None, track, "no_match", []))

        summary = {
            status: sum(entry["status"] == status for entry in entries)
            for status in ("both", "nas_only", "apple_only", "review")
        }
        return {"summary": summary, "entries": entries}

    @staticmethod
    def _artists_are_similar(apple_artist: str, local_artist: str) -> bool:
        """识别艺名附加在本名两侧的保守场景，仅供人工确认。"""
        if not apple_artist or not local_artist or apple_artist == local_artist:
            return False
        shorter, longer = sorted((apple_artist, local_artist), key=len)
        return len(shorter) >= 2 and shorter in longer

    @classmethod
    def _artists_are_compatible(cls, apple_artist: str, local_artist: str) -> bool:
        """仅把相同或明确包含关系的歌手视为人工候选。"""
        return bool(apple_artist and local_artist) and (
            apple_artist == local_artist or cls._artists_are_similar(apple_artist, local_artist)
        )

    @staticmethod
    def _fuzzy_candidates(apple: dict, local: Iterable[dict], rejected: set[tuple[str, str]]) -> list[dict]:
        """只找出名称近似候选，绝不据此自动合并。"""
        title = normalize_title_subject(apple["title"])
        if len(title) < 2:
            return []
        candidates = []
        for track in local:
            if (apple["track_key"], track["id"]) in rejected:
                continue
            if not DualLibraryService._artists_are_compatible(
                apple["normalized_artist"], track["normalized_artist"]
            ):
                continue
            local_title = track["normalized_title_subject"]
            if title == local_title:
                continue
            similarity = difflib.SequenceMatcher(None, title, local_title).ratio()
            if similarity >= 0.72:
                candidates.append((similarity, track))
        return [track for _, track in sorted(candidates, key=lambda item: item[0], reverse=True)[:10]]

    def build_presence_index(self, local_tracks: Iterable[dict]) -> dict[str, set]:
        """构建搜索结果对账索引，避免每个 musicdl 结果重复查询数据库。"""
        self.initialize()
        local = self._prepare_local_tracks(local_tracks)
        with self._connect() as connection:
            self._sync_incremental_confirmations(connection)
            apple = self._latest_tracks(connection)
            incremental = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM apple_incremental_entries WHERE verification_status IN ('pending', 'manual_confirmed', 'confirmed')"
                ).fetchall()
            ]
        pending = [track for track in incremental if track["verification_status"] == "pending"]
        return {
            "local_isrc": {track["isrc"] for track in local if track["isrc"]},
            "local_metadata": {
                (track["normalized_title"], track["normalized_artist"], track["normalized_album"])
                for track in local
            },
            "apple_metadata": {
                (track["normalized_title"], track["normalized_artist"], track["normalized_album"])
                for track in [*apple, *incremental]
            },
            "apple_isrc": {
                track["isrc"] for track in [*apple, *incremental] if track["isrc"]
            },
            "apple_pending_isrc": {track["isrc"] for track in pending if track["isrc"]},
            "apple_pending_metadata": {
                (track["normalized_title"], track["normalized_artist"], track["normalized_album"])
                for track in pending
            },
        }

    @staticmethod
    def lookup_presence(track: dict, index: dict[str, set]) -> dict:
        """判断一个搜索结果是否已存在于本地库和 Apple Music 快照。"""
        isrc = (track.get("isrc") or "").strip().upper()
        metadata = (
            normalize_text(track.get("song_name") or track.get("title")),
            normalize_text(track.get("singers") or track.get("artist")),
            normalize_text(track.get("album")),
        )
        local_by_isrc = bool(isrc and isrc in index["local_isrc"])
        apple_by_isrc = bool(isrc and isrc in index["apple_isrc"])
        local_by_metadata = bool(all(metadata) and metadata in index["local_metadata"])
        apple_by_metadata = bool(all(metadata) and metadata in index["apple_metadata"])
        apple_pending = bool(
            (isrc and isrc in index.get("apple_pending_isrc", set()))
            or (all(metadata) and metadata in index.get("apple_pending_metadata", set()))
        )
        return {
            "nas_present": local_by_isrc or local_by_metadata,
            "apple_present": apple_by_isrc or apple_by_metadata,
            "apple_pending": apple_pending,
            "match_reason": "isrc" if local_by_isrc or apple_by_isrc else "metadata_exact" if local_by_metadata or apple_by_metadata else "no_match",
        }

    @staticmethod
    def _public_local(track: Optional[dict]) -> Optional[dict]:
        if not track:
            return None
        return {
            key: track.get(key)
            for key in ("id", "path", "filename", "title", "artist", "album", "isrc", "format", "duration")
        }

    def _entry(self, status: str, apple: Optional[dict], local: Optional[dict], reason: str, candidates: list[dict]) -> dict:
        public_apple = None
        if apple:
            public_apple = {
                key: apple.get(key)
                for key in ("track_key", "apple_id", "apple_kind", "title", "artist", "album", "isrc")
            }
        return {
            "id": f"{apple.get('track_key')}:{apple.get('row_index')}" if apple else (local or {}).get("id"),
            "status": status,
            "match_reason": reason,
            "apple": public_apple,
            "local": self._public_local(local),
            "candidates": [self._public_local(candidate) for candidate in candidates],
        }


dual_library_service = DualLibraryService()
