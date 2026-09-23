import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.apple_music_handoff import apple_music_handoff_service
from app.services.musicdl_client import MusicdlClientError, musicdl_client
from app.services.dual_library_service import dual_library_service, normalize_text
from app.services.dual_library_config import dual_library_config
from app.services.watch_folder_manager import watch_folder_manager


class AcquisitionService:
    """持久化并执行 musicdl 下载、飞牛写入和 Apple Music 交接任务。"""

    def __init__(self, database_path: Optional[Path] = None):
        self.database_path = database_path or Path(settings.DATA_DIR) / "musicflow.db"
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @contextmanager
    def _connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
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
                CREATE TABLE IF NOT EXISTS acquisition_jobs (
                    id TEXT PRIMARY KEY,
                    selected_track_json TEXT,
                    local_file_id TEXT,
                    local_source_path TEXT,
                    musicdl_download_id TEXT,
                    status TEXT NOT NULL,
                    desired_nas INTEGER NOT NULL,
                    desired_apple INTEGER NOT NULL,
                    nas_status TEXT NOT NULL,
                    apple_status TEXT NOT NULL,
                    staging_path TEXT,
                    nas_path TEXT,
                    apple_import_file TEXT,
                    checksum_sha256 TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create_job(
        self,
        selected_track: Optional[dict],
        local_file_id: Optional[str],
        local_source_path: Optional[str],
        desired_nas: bool,
        desired_apple: bool,
    ) -> dict:
        self.initialize()
        if not desired_nas and not desired_apple:
            raise ValueError("至少选择一个需要补齐的资料库")
        if not selected_track and not local_source_path:
            raise ValueError("缺少 musicdl 搜索结果或本地源文件")
        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO acquisition_jobs (
                    id, selected_track_json, local_file_id, local_source_path, status,
                    desired_nas, desired_apple, nas_status, apple_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    json.dumps(selected_track, ensure_ascii=False) if selected_track else None,
                    local_file_id,
                    local_source_path,
                    int(desired_nas),
                    int(desired_apple),
                    "waiting" if desired_nas else "not_needed",
                    "waiting" if desired_apple else "not_needed",
                    now,
                    now,
                ),
            )
        if desired_apple and selected_track:
            dual_library_service.upsert_incremental_track(
                selected_track,
                source="handoff",
                acquisition_job_id=job_id,
            )
        self.start(job_id)
        return self.get_job(job_id)

    def start(self, job_id: str) -> None:
        with self._lock:
            current = self._threads.get(job_id)
            if current and current.is_alive():
                return
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
            self._threads[job_id] = thread
            thread.start()

    def _run(self, job_id: str) -> None:
        try:
            job = self.get_job(job_id)
            self._update(job_id, status="preparing", error=None)
            source_path = Path(job["staging_path"] or job["local_source_path"] or "")
            if not source_path.is_file():
                source_path = self._download(job_id, job)

            job = self.get_job(job_id)
            errors = []
            accepted_statuses = {"submitted", "success", "handoff_pending", "received_unverified", "confirmed_present"}
            needs_nas = job["desired_nas"] and job["nas_status"] not in accepted_statuses
            needs_apple = job["desired_apple"] and job["apple_status"] not in accepted_statuses
            target_config = dual_library_config.resolve()
            if needs_nas:
                try:
                    watch_path = self._deliver_to_watch_folder(
                        source_path,
                        job_id,
                        target_config["nas_watch_folder_id"],
                        "飞牛",
                    )
                    self._update(job_id, nas_path=str(watch_path), nas_status="submitted")
                except Exception as exc:
                    errors.append(f"提交飞牛监控目录失败：{exc}")
                    self._update(job_id, nas_status="failed")
            if needs_apple:
                try:
                    self._deliver_to_watch_folder(
                        source_path,
                        job_id,
                        target_config["apple_watch_folder_id"],
                        "Apple Music",
                    )
                    self._update(job_id, apple_status="submitted")
                except Exception as exc:
                    errors.append(f"提交 Apple Music 监控目录失败：{exc}")
                    self._update(job_id, apple_status="failed")

            final_job = self.get_job(job_id)
            target_statuses = [
                "success" if final_job["nas_status"] in accepted_statuses else final_job["nas_status"] if final_job["desired_nas"] else "success",
                "success" if final_job["apple_status"] in accepted_statuses else final_job["apple_status"] if final_job["desired_apple"] else "success",
            ]
            final_status = "completed" if all(status == "success" for status in target_statuses) else "partial"
            self._update(job_id, status=final_status, error="；".join(errors) or None)
            if final_status == "completed" and final_job["musicdl_download_id"]:
                try:
                    musicdl_client.cleanup_file(final_job["musicdl_download_id"])
                except MusicdlClientError:
                    pass
            if final_status == "completed" and final_job["staging_path"]:
                staging_path = Path(final_job["staging_path"])
                staging_path.unlink(missing_ok=True)
                try:
                    staging_path.parent.rmdir()
                except OSError:
                    pass
                self._update(job_id, staging_path=None)
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))

    def _download(self, job_id: str, job: dict) -> Path:
        selected = job.get("selected_track") or {}
        token = selected.get("token")
        if not token:
            raise ValueError("musicdl 搜索结果缺少下载令牌")
        download_id = job["musicdl_download_id"] or musicdl_client.start_download(token)
        self._update(job_id, status="downloading", musicdl_download_id=download_id)
        deadline = time.monotonic() + 30 * 60
        while time.monotonic() < deadline:
            result = musicdl_client.get_download(download_id)
            if result.get("status") == "error":
                raise MusicdlClientError(result.get("message") or "musicdl 下载失败")
            if result.get("status") == "done":
                break
            time.sleep(1)
        else:
            raise MusicdlClientError("musicdl 下载超时")

        filename = Path(result.get("filename") or f"{job_id}.audio").name
        staging_path = Path(settings.DATA_DIR) / "acquisitions" / job_id / filename
        _, checksum = musicdl_client.download_file(
            download_id,
            staging_path,
            result.get("checksum_sha256") or "",
        )
        self._update(job_id, status="validating", staging_path=str(staging_path), checksum_sha256=checksum)
        return staging_path

    def _deliver_to_watch_folder(
        self,
        source_path: Path,
        job_id: str,
        watch_folder_id: str,
        target_name: str,
    ) -> Path:
        if not watch_folder_id:
            raise ValueError(f"未配置{target_name}补齐监控目录")
        watch_folder = watch_folder_manager.get_watch_folder(watch_folder_id)
        if not watch_folder:
            raise ValueError(f"{target_name}补齐监控目录不存在")
        if not watch_folder.enabled or not watch_folder.auto_process:
            raise ValueError(f"{target_name}补齐监控目录未启用自动处理")
        target_dir = Path(watch_folder.input_dir)
        if not target_dir.is_dir():
            raise ValueError(f"{target_name}补齐监控目录不可访问")
        target_path = target_dir / source_path.name
        source_checksum = self._sha256(source_path)
        if target_path.exists():
            if self._sha256(target_path) == source_checksum:
                return target_path
            target_path = target_dir / f"{source_path.stem}-{job_id[:8]}{source_path.suffix}"
        temp_path = target_dir / f".{target_path.name}.{uuid.uuid4().hex}.musicflow-copying"
        try:
            shutil.copy2(source_path, temp_path)
            if self._sha256(temp_path) != source_checksum:
                raise IOError("飞牛目标文件校验失败")
            os.replace(temp_path, target_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return target_path

    def mark_nas_delivered(self, source_path: str, output_path: Path) -> None:
        """飞牛成品进入整理媒体库后，再将对应任务标记为已入库。"""
        if not output_path.is_file():
            return
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE acquisition_jobs
                SET nas_status = 'success', updated_at = ?
                WHERE nas_path = ? AND nas_status = 'submitted'
                """,
                (datetime.now(timezone.utc).isoformat(), source_path),
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _update(self, job_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{field} = ?" for field in fields)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE acquisition_jobs SET {assignments} WHERE id = ?",
                (*fields.values(), job_id),
            )

    def get_job(self, job_id: str) -> dict:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM acquisition_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise ValueError("补齐任务不存在")
        return self._public_job(dict(row))

    def list_jobs(self, limit: int = 100) -> list[dict]:
        self.initialize()
        self._refresh_handoff_receipts()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM acquisition_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._public_job(dict(row)) for row in rows]

    def confirm_apple_presence(self) -> int:
        """用最新 Apple Music 快照确认此前交接曲目已进入资料库。"""
        self.initialize()
        with self._connect() as connection:
            apple_rows = connection.execute(
                """
                SELECT t.isrc, t.normalized_title, t.normalized_artist, t.normalized_album
                FROM apple_snapshot_rows r
                JOIN apple_tracks t ON t.track_key = r.track_key
                WHERE r.snapshot_id = (
                    SELECT id FROM apple_library_snapshots ORDER BY imported_at DESC LIMIT 1
                )
                """
            ).fetchall()
            jobs = connection.execute(
                """
                SELECT id, selected_track_json FROM acquisition_jobs
                WHERE desired_apple = 1 AND apple_status IN ('handoff_pending', 'received_unverified')
                """
            ).fetchall()
        apple_isrc = {row["isrc"] for row in apple_rows if row["isrc"]}
        apple_metadata = {
            (row["normalized_title"], row["normalized_artist"], row["normalized_album"])
            for row in apple_rows
        }
        confirmed = 0
        for job in jobs:
            selected = json.loads(job["selected_track_json"] or "{}")
            isrc = (selected.get("isrc") or "").strip().upper()
            metadata = (
                normalize_text(selected.get("song_name") or selected.get("title")),
                normalize_text(selected.get("singers") or selected.get("artist")),
                normalize_text(selected.get("album")),
            )
            if (isrc and isrc in apple_isrc) or (all(metadata) and metadata in apple_metadata):
                self._update(job["id"], apple_status="confirmed_present")
                confirmed += 1
        return confirmed

    def _refresh_handoff_receipts(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, apple_import_file FROM acquisition_jobs
                WHERE apple_status = 'handoff_pending' AND apple_import_file IS NOT NULL
                """
            ).fetchall()
        for row in rows:
            try:
                if apple_music_handoff_service.is_received(row["apple_import_file"]):
                    self._update(row["id"], apple_status="received_unverified")
            except OSError:
                continue

    def retry(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        updates = {"status": "queued", "error": None}
        if job["desired_nas"] and job["nas_status"] == "failed":
            updates["nas_status"] = "waiting"
        if job["desired_apple"] and job["apple_status"] == "failed":
            updates["apple_status"] = "waiting"
        self._update(job_id, **updates)
        self.start(job_id)
        return self.get_job(job_id)

    @staticmethod
    def _public_job(job: dict) -> dict:
        job["desired_nas"] = bool(job["desired_nas"])
        job["desired_apple"] = bool(job["desired_apple"])
        selected_track_json = job.pop("selected_track_json", None)
        job["selected_track"] = json.loads(selected_track_json) if selected_track_json else None
        return job


acquisition_service = AcquisitionService()
