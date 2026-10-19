import hashlib
import asyncio
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
    """持久化并执行 musicdl 下载、本地写入和 Apple Music 交接任务。"""

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
            columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisition_jobs)")}
            if "apple_watch_path" not in columns:
                connection.execute("ALTER TABLE acquisition_jobs ADD COLUMN apple_watch_path TEXT")
            if "apple_delivery_mode" not in columns:
                connection.execute("ALTER TABLE acquisition_jobs ADD COLUMN apple_delivery_mode TEXT")

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
        with self._lock, self._connect() as connection:
            if selected_track:
                identity = ((selected_track.get("isrc") or "").strip().upper(),
                            tuple(normalize_text(selected_track.get(key) or selected_track.get(fallback)) for key, fallback in
                                  (("song_name", "title"), ("singers", "artist"), ("album", "album"))))
                rows = connection.execute("SELECT * FROM acquisition_jobs ORDER BY created_at DESC LIMIT 1000").fetchall()
                for row in rows:
                    previous = json.loads(row["selected_track_json"] or "{}")
                    same = (identity[0] and identity[0] == (previous.get("isrc") or "").strip().upper()) or (
                        all(identity[1]) and identity[1] == tuple(normalize_text(previous.get(key) or previous.get(fallback)) for key, fallback in
                                                                 (("song_name", "title"), ("singers", "artist"), ("album", "album"))))
                    if not same:
                        continue
                    existing = self._public_job(dict(row))
                    if existing["status"] == "failed":
                        continue
                    pending_nas = existing["desired_nas"] and existing["nas_status"] in {"waiting", "submitted", "processing"}
                    pending_apple = existing["desired_apple"] and existing["apple_status"] not in {"failed", "cancelled", "requires_review", "not_needed", "confirmed_present", "cloud_completed"}
                    if (desired_nas and pending_nas) or (desired_apple and pending_apple):
                        if (not desired_nas or pending_nas) and (not desired_apple or pending_apple):
                            return existing
                        raise ValueError("该歌曲已有处理中的任务，请等待完成后再补齐其他目标")
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
                if job["local_source_path"]:
                    raise ValueError("本地源文件不可读取，请重新定位文件或搜索下载")
                source_path = self._download(job_id, job)

            job = self.get_job(job_id)
            errors = []
            accepted_statuses = {"submitted", "success", "handoff_pending", "received_unverified", "confirmed_present"}
            needs_nas = job["desired_nas"] and job["nas_status"] not in accepted_statuses
            needs_apple = job["desired_apple"] and not job.get("apple_upload") and job["apple_status"] not in accepted_statuses
            target_config = dual_library_config.resolve()
            unified_id = target_config.get("unified_watch_folder_id")
            if unified_id and (needs_nas or needs_apple):
                watch_path = self._deliver_to_watch_folder(source_path, job_id, unified_id, "统一", (needs_nas, needs_apple))
                folder = watch_folder_manager.get_watch_folder(unified_id)
                from app.services.profile_manager import profile_manager
                direct = any((profile := profile_manager.get_profile(item.profile_id or "")) and profile.apple_music_delivery_mode == "direct_upload" for item in folder.targets)
                fields = {}
                if needs_nas:
                    fields.update(nas_path=str(watch_path))
                if needs_apple:
                    fields.update(apple_watch_path=str(watch_path), apple_delivery_mode="direct_upload" if direct else "client_import")
                self._update(job_id, **fields)
                needs_nas = needs_apple = False
            if needs_nas:
                try:
                    watch_path = self._deliver_to_watch_folder(
                        source_path,
                        job_id,
                        target_config["nas_watch_folder_id"],
                        "本地",
                    )
                    self._update(job_id, nas_path=str(watch_path), nas_status="submitted")
                except Exception as exc:
                    errors.append(f"提交本地监控目录失败：{exc}")
                    self._update(job_id, nas_status="failed")
            if needs_apple:
                try:
                    apple_watch_path = self._deliver_to_watch_folder(
                        source_path,
                        job_id,
                        target_config["apple_watch_folder_id"],
                        "Apple Music",
                    )
                    from app.services.profile_manager import profile_manager
                    folder = watch_folder_manager.get_watch_folder(target_config["apple_watch_folder_id"])
                    direct_upload = folder and any(
                        (profile := profile_manager.get_profile(target.profile_id or "")) is not None
                        and profile.apple_music_delivery_mode == "direct_upload" for target in folder.targets
                    )
                    self._update(job_id, apple_status="submitted", apple_watch_path=str(apple_watch_path),
                                 apple_delivery_mode="direct_upload" if direct_upload else "client_import")
                    if direct_upload and job.get("selected_track"):
                        dual_library_service.upsert_incremental_track(job["selected_track"], source="direct_upload", acquisition_job_id=job_id)
                except Exception as exc:
                    errors.append(f"提交 Apple Music 监控目录失败：{exc}")
                    self._update(job_id, apple_status="failed")

            final_job = self.get_job(job_id)
            target_statuses = [
                "success" if final_job["nas_status"] in accepted_statuses else final_job["nas_status"] if final_job["desired_nas"] else "success",
                "success" if final_job.get("apple_upload") or final_job["apple_status"] in accepted_statuses else final_job["apple_status"] if final_job["desired_apple"] else "success",
            ]
            final_status = "completed" if unified_id or all(status == "success" for status in target_statuses) else "partial"
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
        routing: Optional[tuple[bool, bool]] = None,
    ) -> Path:
        if not watch_folder_id:
            raise ValueError(f"未配置{target_name}补齐监控目录")
        watch_folder = watch_folder_manager.get_watch_folder(watch_folder_id)
        if not watch_folder:
            raise ValueError(f"{target_name}补齐监控目录不存在")
        if not watch_folder.input_dir:
            raise ValueError(f"{target_name}处理方案未配置监控目录，不能用于发现音乐自动投递")
        if not watch_folder.enabled or not watch_folder.auto_process:
            raise ValueError(f"{target_name}补齐监控目录未启用自动处理")
        if routing:
            from app.services.watch_routing import target_library
            available = {target_library(item) for item in watch_folder.targets}
            needed = ({"nas"} if routing[0] else set()) | ({"apple"} if routing[1] else set())
            if not needed <= available:
                raise ValueError("统一入口缺少本次目标的输出规则")
        target_dir = Path(watch_folder.input_dir)
        if not target_dir.is_dir():
            raise ValueError(f"{target_name}补齐监控目录不可访问")
        source_checksum = self._sha256(source_path)
        temp_path = target_dir / f".{source_path.name}.{uuid.uuid4().hex}.musicflow-copying"
        try:
            shutil.copy2(source_path, temp_path)
            if self._sha256(temp_path) != source_checksum:
                raise IOError("本地目标文件校验失败")
            number = 1
            while True:
                name = source_path.name if number == 1 else f"{source_path.stem} ({number}){source_path.suffix}"
                target_path = target_dir / name
                exists = target_path.exists() or target_path.is_symlink()
                if exists and (target_path.is_symlink() or not target_path.is_file() or self._sha256(target_path) != source_checksum):
                    number += 1
                    continue
                # 硬链接原子发布完整文件，目标已存在时绝不覆盖。
                publish = None if exists else lambda: os.link(temp_path, target_path)
                try:
                    if routing:
                        from app.services.watch_routing import watch_routing
                        fields = {}
                        if routing[0]:
                            fields.update(nas_path=str(target_path), nas_status="submitted")
                        if routing[1]:
                            fields.update(apple_watch_path=str(target_path), apple_status="submitted")
                        self._update(job_id, **fields)
                        watch_routing.register(watch_folder, target_path, target_path if exists else temp_path,
                                               *routing, merge=True, job_id=job_id, publish=publish)
                    elif publish:
                        publish()
                    break
                except FileExistsError:
                    # 并发任务先发布时重新核对内容，只有内容不同时才换名。
                    continue
            if routing and watch_folder_manager.loop and watch_folder_manager.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    watch_folder_manager._process_file(watch_folder, str(target_path), "acquisition", wait=True),
                    watch_folder_manager.loop,
                ).add_done_callback(watch_folder_manager._log_callback_error)
            return target_path
        finally:
            temp_path.unlink(missing_ok=True)

    def mark_nas_delivered(self, source_path: str, output_path: Path) -> None:
        """本地成品进入整理媒体库后，再将对应任务标记为已入库。"""
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
                SELECT id, selected_track_json, apple_watch_path, apple_delivery_mode FROM acquisition_jobs
                WHERE desired_apple = 1 AND (apple_status IN ('handoff_pending', 'received_unverified')
                    OR (apple_status = 'submitted' AND apple_watch_path IS NOT NULL))
                """
            ).fetchall()
        apple_isrc = {row["isrc"] for row in apple_rows if row["isrc"]}
        apple_metadata = {
            (row["normalized_title"], row["normalized_artist"], row["normalized_album"])
            for row in apple_rows
        }
        confirmed = 0
        for job in jobs:
            if job["apple_watch_path"] and job["apple_delivery_mode"] == "direct_upload":
                from app.services.apple_music_upload import apple_music_upload_service
                upload = apple_music_upload_service.for_source(job["apple_watch_path"])
                if not upload or upload["state"] != "cloud_completed":
                    continue
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
        from app.services.watch_routing import watch_routing
        routed = watch_routing.for_source(job.get("nas_path") or job.get("apple_watch_path"))
        if routed:
            folder_id, plan = routed
            if not watch_folder_manager.loop or not watch_folder_manager.loop.is_running():
                raise ValueError("监控服务尚未就绪")
            libraries = {library for library in ("nas", "apple") if job[f"desired_{library}"]}
            asyncio.run_coroutine_threadsafe(self._retry_routed_outputs(folder_id, plan, libraries), watch_folder_manager.loop).result(timeout=30)
            return self.get_job(job_id)
        if job.get("apple_upload"):
            from app.services.apple_music_upload import apple_music_upload_service
            upload = job["apple_upload"]
            if upload["allowed_actions"]:
                apple_music_upload_service.retry(upload["id"], upload["allowed_actions"][0])
            if job["nas_status"] != "failed":
                return self.get_job(job_id)
        updates = {"status": "queued", "error": None}
        if job["desired_nas"] and job["nas_status"] == "failed":
            updates["nas_status"] = "waiting"
        if job["desired_apple"] and job["apple_status"] == "failed":
            updates["apple_status"] = "waiting"
        self._update(job_id, **updates)
        self.start(job_id)
        return self.get_job(job_id)

    async def _retry_routed_outputs(self, folder_id, plan, libraries=None):
        from app.api.routes.tasks import tasks_cache, retry_task, retry_task_apple_music_handoff
        from app.services.watch_routing import watch_routing
        from app.services.apple_music_upload import apple_music_upload_service

        for item in plan["outputs"]:
            if libraries is not None and item["library"] not in libraries:
                continue
            task = tasks_cache.get(item.get("task_id"))
            if not task:
                if item["state"] == "failed" and not item.get("task_id"):
                    item.update(state="waiting", error=None)
                continue
            upload = apple_music_upload_service.for_task(task.id)
            if upload:
                if upload["allowed_actions"]:
                    await asyncio.to_thread(apple_music_upload_service.retry, upload["id"], upload["allowed_actions"][0])
            elif task.status.value == "failed":
                retried = await retry_task(task.id)
                item["task_id"] = retried.id
            elif task.apple_music_status == "failed":
                await retry_task_apple_music_handoff(task.id)
        watch_routing.save(folder_id, plan["path"], plan)
        folder = watch_folder_manager.get_watch_folder(folder_id)
        if folder:
            await watch_folder_manager._process_file(folder, plan["path"], "retry")

    def _public_job(self, job: dict) -> dict:
        job["desired_nas"] = bool(job["desired_nas"])
        job["desired_apple"] = bool(job["desired_apple"])
        selected_track_json = job.pop("selected_track_json", None)
        job["selected_track"] = json.loads(selected_track_json) if selected_track_json else None
        from app.services.watch_routing import watch_routing
        routed = watch_routing.for_source(job.get("nas_path") or job.get("apple_watch_path"))
        if routed:
            _, plan = routed
            for library, field in (("nas", "nas_status"), ("apple", "apple_status")):
                if not job[f"desired_{library}"] or job[field] == "confirmed_present":
                    continue
                states = [watch_routing.output_status(item) for item in plan["outputs"] if item["library"] == library]
                if not states:
                    continue
                if any(state in {"failed", "blocked"} for state in states):
                    job[field] = "failed"
                elif any(state in {"skipped", "requires_review"} for state in states):
                    job[field] = "requires_review"
                elif all(state == "success" for state in states):
                    job[field] = "success"
                else:
                    job[field] = states[0] if len(set(states)) == 1 and states[0] in {"handoff_pending", "received_unverified"} else "processing"
        if job.get("apple_watch_path"):
            from app.services.apple_music_upload import apple_music_upload_service
            upload = apple_music_upload_service.for_source(job["apple_watch_path"])
            if upload:
                job["apple_upload"] = upload
                if job["apple_status"] != "confirmed_present":
                    job["apple_status"] = upload["state"]
        if routed:
            states = [job[field] for field in ("nas_status", "apple_status") if job[field] != "not_needed"]
            if any(state in {"failed", "requires_review", "cancelled", "stopped"} for state in states):
                job["status"] = "partial"
            elif all(state in {"success", "confirmed_present", "cloud_completed"} for state in states):
                job["status"] = "completed"
            elif all(state in {"success", "confirmed_present", "cloud_completed", "received_unverified", "handoff_pending"} for state in states):
                job["status"] = "awaiting_confirmation"
            else:
                job["status"] = "processing"
        job["routing_managed"] = bool(routed)
        return job


acquisition_service = AcquisitionService()
