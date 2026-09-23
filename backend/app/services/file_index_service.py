import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from app.config import settings


class FileIndexService:
    """在 SQLite 中保存文件元数据，并按文件属性执行增量扫描。"""

    def __init__(self, database_path: Optional[Path] = None):
        self.database_path = database_path or Path(settings.DATA_DIR) / "musicflow.db"
        self._lock = threading.RLock()

    @contextmanager
    def _connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_index (
                    scope TEXT NOT NULL,
                    path TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (scope, path)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_index_state (
                    scope TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 0,
                    last_scan_at TEXT,
                    last_error TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_index_scope_source ON file_index(scope, source_path)"
            )

    def has_snapshot(self, scope: str) -> bool:
        self.initialize()
        with self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM file_index_state WHERE scope = ?",
                (scope,),
            ).fetchone() is not None

    def load(self, scope: str) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT data_json FROM file_index WHERE scope = ? ORDER BY path",
                (scope,),
            ).fetchall()
        return [json.loads(row["data_json"]) for row in rows]

    def get_version(self, scope: str) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM file_index_state WHERE scope = ?",
                (scope,),
            ).fetchone()
        return int(row["version"]) if row else 0

    def refresh(
        self,
        scope: str,
        sources: Iterable[str],
        reader: Callable[[Path], Optional[dict]],
    ) -> list[dict]:
        """只重读新增或属性变化的文件；不可访问目录保留旧记录。"""
        self.initialize()
        normalized_sources = list(dict.fromkeys(str(Path(source).expanduser()) for source in sources))
        supported = {extension.lower().lstrip(".") for extension in settings.SUPPORTED_FORMATS}
        now = datetime.now(timezone.utc).isoformat()
        errors = []
        changed = False

        with self._lock, self._connect() as connection:
            existing_rows = connection.execute(
                "SELECT path, source_path, size, mtime_ns, data_json FROM file_index WHERE scope = ?",
                (scope,),
            ).fetchall()
            existing = {row["path"]: row for row in existing_rows}

            removed_sources = {row["source_path"] for row in existing_rows} - set(normalized_sources)
            for source in removed_sources:
                connection.execute(
                    "DELETE FROM file_index WHERE scope = ? AND source_path = ?",
                    (scope, source),
                )
                changed = True

            for source in normalized_sources:
                source_path = Path(source)
                try:
                    candidates = self._iter_audio_files(source_path, supported)
                    seen = set()
                    for path in candidates:
                        normalized_path = str(path)
                        seen.add(normalized_path)
                        try:
                            stat = path.stat()
                        except OSError as exc:
                            errors.append(f"{normalized_path}: {exc}")
                            continue
                        previous = existing.get(normalized_path)
                        if (
                            previous
                            and int(previous["size"]) == stat.st_size
                            and int(previous["mtime_ns"]) == stat.st_mtime_ns
                        ):
                            if previous["source_path"] != source:
                                connection.execute(
                                    "UPDATE file_index SET source_path = ? WHERE scope = ? AND path = ?",
                                    (source, scope, normalized_path),
                                )
                                changed = True
                            continue

                        reusable = connection.execute(
                            """
                            SELECT data_json FROM file_index
                            WHERE path = ? AND size = ? AND mtime_ns = ?
                            LIMIT 1
                            """,
                            (normalized_path, stat.st_size, stat.st_mtime_ns),
                        ).fetchone()
                        data = json.loads(reusable["data_json"]) if reusable else reader(path)
                        if data is None:
                            errors.append(f"{normalized_path}: 无法读取音频信息")
                            continue
                        connection.execute(
                            """
                            INSERT INTO file_index(scope, path, source_path, size, mtime_ns, data_json)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(scope, path) DO UPDATE SET
                                source_path = excluded.source_path,
                                size = excluded.size,
                                mtime_ns = excluded.mtime_ns,
                                data_json = excluded.data_json
                            """,
                            (
                                scope,
                                normalized_path,
                                source,
                                stat.st_size,
                                stat.st_mtime_ns,
                                json.dumps(data, ensure_ascii=False),
                            ),
                        )
                        changed = True

                    stale_paths = [
                        row["path"]
                        for row in existing_rows
                        if row["source_path"] == source and row["path"] not in seen
                    ]
                    for stale_path in stale_paths:
                        connection.execute(
                            "DELETE FROM file_index WHERE scope = ? AND path = ?",
                            (scope, stale_path),
                        )
                        changed = True
                except (OSError, PermissionError) as exc:
                    errors.append(f"{source}: {exc}")

            current_version = self._version_in_connection(connection, scope)
            next_version = current_version + 1 if changed else current_version
            connection.execute(
                """
                INSERT INTO file_index_state(scope, version, last_scan_at, last_error)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                    version = excluded.version,
                    last_scan_at = excluded.last_scan_at,
                    last_error = excluded.last_error
                """,
                (scope, next_version, now, "；".join(errors[:10]) or None),
            )

        return self.load(scope)

    def upsert(self, scope: str, source_path: str, data: dict) -> None:
        path = Path(data["path"])
        stat = path.stat()
        self.initialize()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO file_index(scope, path, source_path, size, mtime_ns, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, path) DO UPDATE SET
                    source_path = excluded.source_path,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    data_json = excluded.data_json
                """,
                (scope, str(path), source_path, stat.st_size, stat.st_mtime_ns, json.dumps(data, ensure_ascii=False)),
            )
            self._bump_version(connection, scope)

    def remove_path(self, scope: str, path: str) -> None:
        self.initialize()
        with self._lock, self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM file_index WHERE scope = ? AND path = ?",
                (scope, path),
            ).rowcount
            if deleted:
                self._bump_version(connection, scope)

    def remove_source(self, scope: str, source_path: str) -> None:
        self.initialize()
        with self._lock, self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM file_index WHERE scope = ? AND source_path = ?",
                (scope, source_path),
            ).rowcount
            if deleted:
                self._bump_version(connection, scope)

    @staticmethod
    def _iter_audio_files(source: Path, supported: set[str]):
        if source.is_file():
            return [source] if source.suffix.lower().lstrip(".") in supported else []
        if not source.is_dir():
            raise FileNotFoundError(f"目录不可访问：{source}")
        return [
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower().lstrip(".") in supported
        ]

    @staticmethod
    def _version_in_connection(connection: sqlite3.Connection, scope: str) -> int:
        row = connection.execute(
            "SELECT version FROM file_index_state WHERE scope = ?",
            (scope,),
        ).fetchone()
        return int(row["version"]) if row else 0

    def _bump_version(self, connection: sqlite3.Connection, scope: str) -> None:
        version = self._version_in_connection(connection, scope) + 1
        connection.execute(
            """
            INSERT INTO file_index_state(scope, version, last_scan_at, last_error)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(scope) DO UPDATE SET version = excluded.version, last_scan_at = excluded.last_scan_at
            """,
            (scope, version, datetime.now(timezone.utc).isoformat()),
        )


file_index_service = FileIndexService()
