"""持久化独立上传任务；Apple 授权和票据由上传执行器加密保存。"""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from app.config import settings


UPLOAD_STATES = {
    "queued", "waiting_worker", "waiting_authorization", "waiting_client_exit",
    "staging", "validating", "uploading", "cloud_processing",
    "media_completed_extras_pending", "cloud_completed", "requires_review", "failed", "cancelled", "stopping", "stopped",
}
RESUME_ACTIONS = {"upload", "resume_pending", "resume_work", "upload_media_extras", "report_completed"}
TERMINAL_STATES = {"cloud_completed", "requires_review", "failed", "cancelled", "media_completed_extras_pending", "stopped"}
ERRORS = {
    "authorization_required": "请在桌面客户端重新获取授权并导入服务端",
    "client_running": "请正常退出 Apple Music 和资料库进程",
    "unsupported_fingerprint": "当前不支持此歌曲要求的指纹分支",
    "unsupported_media": "仅支持单音轨 AAC LC M4A",
    "incompatible_version": "官方客户端二进制版本不兼容",
    "content_changed": "成品已变化或下载校验失败",
    "context_mismatch": "当前授权与绑定资料库不一致",
    "request_uncertain": "请求结果不确定，需要核对本地记录",
    "session_changed": "Apple 返回了其他上传会话，已停止处理并保留原任务记录；请核对并发上传与原会话",
    "upload_failed": "上传未完成，请核对上传执行器的加密记录",
    "stalled": "上传长期无进展，已停止本地执行并保留恢复记录",
    "worker_interrupted": "上传进程已退出，已保留恢复记录",
}


class UploadConflict(ValueError):
    """拒绝越权、过期或不安全的任务变更。"""


class AppleMusicUploadService:
    LEASE_SECONDS = 120

    def __init__(self, database_path=None):
        self.database_path = Path(database_path or Path(settings.DATA_DIR) / "musicflow.db")

    @contextmanager
    def connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS upload_worker (
                    id TEXT PRIMARY KEY, account_scope TEXT NOT NULL, token_hash TEXT NOT NULL,
                    last_seen REAL, readiness TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS apple_uploads (
                    id TEXT PRIMARY KEY, account_scope TEXT NOT NULL, source_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL, size INTEGER NOT NULL, state TEXT NOT NULL,
                    stage TEXT, error_code TEXT, action TEXT NOT NULL DEFAULT 'upload',
                    worker_id TEXT, lease_token TEXT, lease_until REAL,
                    sequence INTEGER NOT NULL DEFAULT 0, evidence TEXT NOT NULL DEFAULT '{}',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    bytes_sent INTEGER, bytes_total INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    signature_progress INTEGER, signature_elapsed_seconds REAL,
                    UNIQUE(account_scope, sha256)
                );
                CREATE TABLE IF NOT EXISTS apple_upload_links (
                    conversion_task_id TEXT PRIMARY KEY, upload_id TEXT NOT NULL, source_file TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS apple_upload_timeline (
                    id INTEGER PRIMARY KEY, upload_id TEXT NOT NULL, stage TEXT, state TEXT NOT NULL,
                    started_at REAL NOT NULL, ended_at REAL, stage_token REAL,
                    progress REAL, wait_until REAL, bytes_sent INTEGER, bytes_total INTEGER
                );
                CREATE INDEX IF NOT EXISTS apple_upload_timeline_job ON apple_upload_timeline(upload_id, id);
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(apple_uploads)")}
            additions = {"signature_progress": "INTEGER", "signature_elapsed_seconds": "REAL",
                         "stop_requested": "INTEGER NOT NULL DEFAULT 0", "running": "INTEGER NOT NULL DEFAULT 0",
                         "deleted": "INTEGER NOT NULL DEFAULT 0", "queued_at": "REAL"}
            if not additions.keys() <= columns:
                connection.execute("BEGIN IMMEDIATE")
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(apple_uploads)")}
                for name, kind in additions.items():
                    if name not in columns:
                        connection.execute(f"ALTER TABLE apple_uploads ADD COLUMN {name} {kind}")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(apple_upload_links)")}
            if "deleted" not in columns:
                try:
                    connection.execute("ALTER TABLE apple_upload_links ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    if "deleted" not in {row["name"] for row in connection.execute("PRAGMA table_info(apple_upload_links)")}:
                        raise

    def bind_worker(self, save_binding=None):
        """仅由后端本地管理命令调用；首版不自动替换已有绑定。"""
        self.initialize()
        token = secrets.token_urlsafe(48)
        worker_id, scope = str(uuid.uuid4()), str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM upload_worker").fetchone():
                raise UploadConflict("已有工作进程绑定，请保留原配置；首版不支持自动换机")
            connection.execute("INSERT INTO upload_worker(id, account_scope, token_hash) VALUES (?, ?, ?)",
                               (worker_id, scope, hashlib.sha256(token.encode()).hexdigest()))
            binding = {"worker_id": worker_id, "account_scope": scope, "token": token, "protocol_version": 1}
            if save_binding:
                save_binding(binding)
        return binding

    def worker_status(self):
        self.initialize()
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM upload_worker LIMIT 1").fetchone()
            active = connection.execute("SELECT COUNT(*) FROM apple_uploads WHERE running = 1 OR (lease_until >= ? AND state NOT IN ('cloud_completed','requires_review','failed','cancelled','media_completed_extras_pending','stopped'))", (time.time(),)).fetchone()[0]
            queued = connection.execute("SELECT COUNT(*) FROM apple_uploads WHERE state = 'queued' AND deleted = 0").fetchone()[0]
        counts = {"concurrency": settings.APPLE_MUSIC_UPLOAD_CONCURRENCY, "active_count": active, "queued_count": queued}
        if row is None:
            return {"bound": False, "online": False, **counts}
        return {"bound": True, "worker_id": row["id"], "account_scope": row["account_scope"],
                "online": bool(row["last_seen"] and time.time() - row["last_seen"] < self.LEASE_SECONDS),
                "last_seen": row["last_seen"], **json.loads(row["readiness"]), **counts}

    def authenticate(self, worker_id, token):
        self.initialize()
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM upload_worker WHERE id = ?", (worker_id,)).fetchone()
        if not row or not secrets.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise PermissionError("工作进程凭据无效")
        return row["account_scope"]

    @staticmethod
    def checksum(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def enqueue(self, task_id, source_file, output_file, account_scope):
        self.initialize()
        path = Path(output_file)
        if not path.is_file() or path.is_symlink() or path.suffix.lower() != ".m4a":
            raise UploadConflict("上传成品必须是已完成的 M4A 普通文件")
        if path.absolute() != path.resolve(strict=True):
            raise UploadConflict("成品路径不能经过符号链接或越界目录")
        # 固定解析后的成品路径，拒绝后续父目录符号链接替换。
        path = path.resolve(strict=True)
        digest, size, now = self.checksum(path), path.stat().st_size, time.time()
        worker = self.worker_status()
        if not account_scope or worker.get("account_scope") != account_scope:
            raise UploadConflict("服务端上传执行器尚未关联当前资料库")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT upload_id FROM apple_upload_links WHERE conversion_task_id = ?", (task_id,)).fetchone()
            if previous:
                return self.get(previous["upload_id"])
            job_id = str(uuid.uuid4())
            inserted = connection.execute("""INSERT OR IGNORE INTO apple_uploads
                (id, account_scope, source_path, sha256, size, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)""",
                (job_id, account_scope, str(path), digest, size, now, now))
            if inserted.rowcount:
                connection.execute("INSERT INTO apple_upload_timeline(upload_id, stage, state, started_at) VALUES (?, 'queued', 'queued', ?)", (job_id, now))
            row = connection.execute("SELECT id FROM apple_uploads WHERE account_scope = ? AND sha256 = ?", (account_scope, digest)).fetchone()
            connection.execute("INSERT INTO apple_upload_links(conversion_task_id, upload_id, source_file) VALUES (?, ?, ?)", (task_id, row["id"], source_file))
            job_id = row["id"]
        return self.get(job_id)

    def get(self, job_id):
        self.initialize()
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            timeline = [dict(item) for item in connection.execute(
                "SELECT stage, state, started_at, ended_at, progress, wait_until, bytes_sent, bytes_total FROM apple_upload_timeline WHERE upload_id = ? ORDER BY id", (job_id,))]
        if not row:
            raise KeyError("上传任务不存在")
        result = {key: row[key] for key in ("id", "state", "stage", "sha256", "size", "bytes_sent", "bytes_total", "created_at", "updated_at", "signature_progress", "signature_elapsed_seconds")}
        result["error_code"] = row["error_code"]
        finished = row["updated_at"] if row["state"] in TERMINAL_STATES else None
        result.update(timeline=timeline, finished_at=finished, server_time=time.time(),
                      elapsed_seconds=max(0, (finished or time.time()) - row["created_at"]))
        for item in timeline:
            item["elapsed_seconds"] = max(0, (item["ended_at"] or finished or time.time()) - item["started_at"])
        result["error"] = ERRORS.get(row["error_code"])
        result["allowed_actions"] = [row["action"]] if row["state"] in {"failed", "media_completed_extras_pending", "stopped", "cancelled"} and row["action"] != "report_completed" and not row["running"] and not row["deleted"] else []
        result.update(running=bool(row["running"]), deleted=bool(row["deleted"]), stop_requested=bool(row["stop_requested"]),
                      can_stop=row["state"] not in TERMINAL_STATES | {"queued", "stopping"},
                      can_delete=row["state"] in TERMINAL_STATES and not row["running"])
        with self.connect() as connection:
            result["sources"] = [dict(item) for item in connection.execute("SELECT conversion_task_id, source_file FROM apple_upload_links WHERE upload_id = ? AND deleted = 0", (job_id,))]
        if row["error_code"] in {"unsupported_fingerprint", "unsupported_media", "context_mismatch"}:
            result["allowed_actions"] = []
        if row["state"] == "queued" and not self.worker_status()["online"]:
            result["state"] = "waiting_worker"
        elif row["state"] == "queued":
            worker = self.worker_status()
            if not worker.get("authorization_saved"):
                result["state"] = "waiting_authorization"
            elif not worker.get("client_exited"):
                result["state"] = "waiting_client_exit"
            elif not worker.get("compatible"):
                result.update(state="waiting_worker", error_code="incompatible_version", error=ERRORS["incompatible_version"])
            elif not worker.get("context_matches"):
                result.update(state="waiting_authorization", error_code="context_mismatch", error=ERRORS["context_mismatch"])
        return result

    def for_task(self, task_id):
        self.initialize()
        with self.connect() as connection:
            row = connection.execute("SELECT upload_id FROM apple_upload_links WHERE conversion_task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        result = self.get(row["upload_id"])
        with self.connect() as connection:
            link = connection.execute("SELECT deleted FROM apple_upload_links WHERE conversion_task_id = ?", (task_id,)).fetchone()
        result["deleted"] = result["deleted"] or bool(link["deleted"])
        if result["deleted"]:
            result["allowed_actions"] = []
        return result

    def for_source(self, source_file):
        self.initialize()
        with self.connect() as connection:
            row = connection.execute("""SELECT l.upload_id FROM apple_upload_links l JOIN apple_uploads u ON u.id = l.upload_id
                WHERE l.source_file = ? ORDER BY u.created_at DESC LIMIT 1""", (source_file,)).fetchone()
        return self.get(row["upload_id"]) if row else None

    def claim(self, worker_id, scope, readiness, managed=False):
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE upload_worker SET last_seen = ?, readiness = ? WHERE id = ?",
                               (now, json.dumps(readiness), worker_id))
            if not all(readiness.get(key) for key in ("authorization_saved", "client_exited", "compatible", "context_matches")):
                return None
            # 过期任务只交还原工作进程，由本地记录决定能否恢复。
            row = connection.execute("""SELECT * FROM apple_uploads WHERE account_scope = ? AND
                ((worker_id = ? AND running = 0 AND lease_token IS NOT NULL AND lease_until < ? AND state NOT IN
                  ('cloud_completed', 'requires_review', 'failed', 'cancelled', 'media_completed_extras_pending', 'stopped')) OR
                 (state = 'queued' AND lease_token IS NULL AND deleted = 0))
                ORDER BY CASE WHEN lease_token IS NOT NULL THEN 0 ELSE 1 END, COALESCE(queued_at, created_at), id LIMIT 1""", (scope, worker_id, now)).fetchone()
            if not row:
                return None
            active = connection.execute("""SELECT COUNT(*) FROM apple_uploads WHERE id != ? AND account_scope = ? AND
                (running = 1 OR (lease_token IS NOT NULL AND lease_until >= ? AND state NOT IN
                ('cloud_completed', 'requires_review', 'failed', 'cancelled', 'media_completed_extras_pending', 'stopped')))""", (row['id'], scope, now)).fetchone()[0]
            if active >= (settings.APPLE_MUSIC_UPLOAD_CONCURRENCY if managed else 1):
                return None
            lease = secrets.token_urlsafe(32)
            connection.execute("""UPDATE apple_uploads SET worker_id = ?, lease_token = ?, lease_until = ?,
                sequence = 0, state = CASE WHEN stop_requested = 1 THEN 'stopping' ELSE 'staging' END,
                running = ?, updated_at = ? WHERE id = ?""",
                (worker_id, lease, now + self.LEASE_SECONDS, int(managed), now, row["id"]))
        return {"job_id": row["id"], "lease_token": lease, "lease_until": now + self.LEASE_SECONDS,
                "sha256": row["sha256"], "size": row["size"], "action": row["action"], "attempt": row["attempt"],
                "recovery_required": bool(row["lease_token"]),
                "stop_requested": bool(row["stop_requested"]),
                "content_url": f"/api/apple-music/uploads/{row['id']}/content"}

    @staticmethod
    def check_lease(row, worker_id, lease):
        if not row or row["worker_id"] != worker_id or not row["lease_token"] or not secrets.compare_digest(row["lease_token"], lease) or row["lease_until"] < time.time():
            raise UploadConflict("上传租约无效或已过期")

    def content(self, job_id, worker_id, lease):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
        self.check_lease(row, worker_id, lease)
        path = Path(row["source_path"])
        if not path.is_file() or path.is_symlink() or str(path.resolve()) != row["source_path"] or path.stat().st_size != row["size"] or self.checksum(path) != row["sha256"]:
            raise UploadConflict("成品不存在或已变化，拒绝上传")
        return path

    def event(self, job_id, worker_id, event):
        state, action = event["state"], event.get("action", "upload")
        if state not in UPLOAD_STATES or action not in RESUME_ACTIONS:
            raise UploadConflict("上传状态或恢复动作无效")
        evidence = event.get("evidence", {})
        if state == "cloud_completed" and not all(evidence.get(key) is True for key in ("complete_received", "all_work_completed", "extras_completed")):
            raise UploadConflict("缺少协议或资产完成证据")
        if event.get("error_code") and event["error_code"] not in ERRORS:
            raise UploadConflict("上传错误码无效")
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            self.check_lease(row, worker_id, event["lease_token"])
            if event["sequence"] <= row["sequence"]:
                return {"accepted": True, "sequence": row["sequence"], "stop_requested": bool(row["stop_requested"])}
            if event["sequence"] != row["sequence"] + 1:
                raise UploadConflict("事件序号不连续")
            if row["state"] in TERMINAL_STATES:
                raise UploadConflict("终态任务不能继续上报新阶段")
            if state in {"queued", "waiting_worker"}:
                raise UploadConflict("工作进程不能重置上传队列")
            terminal = state in TERMINAL_STATES
            if row["stop_requested"] and not terminal:
                state = "stopping"
                event = {**event, "state": state}
            self.record_timing(connection, row, event, now, terminal)
            connection.execute("""UPDATE apple_uploads SET state = ?, stage = ?, error_code = ?, action = ?, evidence = ?,
                bytes_sent = ?, bytes_total = ?, signature_progress = ?, signature_elapsed_seconds = ?, sequence = ?, lease_until = ?, updated_at = ? WHERE id = ?""",
                (state, event.get("stage"), event.get("error_code"), action, json.dumps(evidence),
                 event.get("bytes_sent"), event.get("bytes_total"), event.get("signature_progress"), event.get("signature_elapsed_seconds"), event["sequence"], now + self.LEASE_SECONDS, now, job_id))
            # 保留终态租约以便丢失响应时幂等重报；不再重新领取终态任务。
            if terminal:
                connection.execute("UPDATE apple_uploads SET lease_until = ? WHERE id = ?", (now + 86400, job_id))
            connection.execute("UPDATE upload_worker SET last_seen = ? WHERE id = ?", (now, worker_id))
        return {"accepted": True, "sequence": event["sequence"], "stop_requested": bool(row["stop_requested"])}

    def list_uploads(self):
        self.initialize()
        with self.connect() as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM apple_uploads WHERE deleted = 0 ORDER BY created_at DESC LIMIT 100")]
        return [self.get(job_id) for job_id in ids]

    @staticmethod
    def record_timing(connection, row, event, now, terminal=False):
        """使用服务端时钟记录阶段；同一序号的重报在调用前排除。"""
        last = connection.execute("SELECT * FROM apple_upload_timeline WHERE upload_id = ? ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
        changed = (last is None or last["ended_at"] is not None or last["stage"] != event.get("stage")
                   or last["state"] != event["state"] or last["stage_token"] != event.get("stage_token"))
        if changed or terminal:
            connection.execute("UPDATE apple_upload_timeline SET ended_at = ? WHERE upload_id = ? AND ended_at IS NULL", (now, row["id"]))
        if not terminal and changed:
            connection.execute("INSERT INTO apple_upload_timeline(upload_id, stage, state, started_at, stage_token) VALUES (?, ?, ?, ?, ?)",
                               (row["id"], event.get("stage"), event["state"], now, event.get("stage_token")))
        if not terminal:
            connection.execute("""UPDATE apple_upload_timeline SET progress = ?, bytes_sent = ?, bytes_total = ?,
                wait_until = COALESCE(wait_until, ?) WHERE upload_id = ? AND ended_at IS NULL""",
                (event.get("stage_progress"), event.get("bytes_sent"), event.get("bytes_total"),
                 now + event["wait_seconds"] if event.get("wait_seconds") is not None else None, row["id"]))

    def retry(self, job_id, action):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise KeyError("上传任务不存在")
            if row["running"] or row["deleted"] or row["state"] not in {"failed", "media_completed_extras_pending", "stopped", "cancelled"} or row["action"] != action or action == "report_completed" or row["error_code"] in {"unsupported_fingerprint", "unsupported_media", "context_mismatch"}:
                raise UploadConflict("当前任务不允许此恢复动作，请核对本地记录")
            connection.execute("UPDATE apple_uploads SET state = 'queued', stop_requested = 0, lease_token = NULL, lease_until = NULL, signature_progress = NULL, signature_elapsed_seconds = NULL, attempt = attempt + 1, queued_at = ?, updated_at = ? WHERE id = ?",
                               (time.time(), time.time(), job_id))
            connection.execute("INSERT INTO apple_upload_timeline(upload_id, stage, state, started_at) VALUES (?, 'queued', 'queued', ?)", (job_id, time.time()))
        return self.get(job_id)

    def stop(self, job_id):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise KeyError("上传任务不存在")
            if row["state"] in TERMINAL_STATES:
                return self.get(job_id)
            if row["state"] == "queued":
                raise UploadConflict("尚未执行的任务请取消排队")
            connection.execute("UPDATE apple_uploads SET stop_requested = 1, state = 'stopping' WHERE id = ?", (job_id,))
        return self.get(job_id)

    def delete(self, job_id, task_id=None):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise KeyError("上传任务不存在")
            if row["running"] or row["state"] not in TERMINAL_STATES:
                raise UploadConflict("请先取消排队或停止上传，等待进程退出后再删除记录")
            if task_id is not None:
                changed = connection.execute("UPDATE apple_upload_links SET deleted = 1 WHERE upload_id = ? AND conversion_task_id = ?", (job_id, task_id))
                if not changed.rowcount:
                    raise UploadConflict("记录不属于此上传任务")
            else:
                connection.execute("UPDATE apple_uploads SET deleted = 1 WHERE id = ?", (job_id,))
        return {"deleted": True}

    def controls(self, worker_id, readiness):
        """仅向已认证执行器提供其任务租约，用于进程退出后的收尾。"""
        with self.connect() as connection:
            connection.execute("UPDATE upload_worker SET last_seen = ?, readiness = ? WHERE id = ?", (time.time(), json.dumps(readiness), worker_id))
            connection.execute("UPDATE apple_uploads SET lease_until = ? WHERE worker_id = ? AND running = 1", (time.time() + self.LEASE_SECONDS, worker_id))
            rows = connection.execute("SELECT id, sha256, attempt, lease_token, sequence, state, stop_requested, running FROM apple_uploads WHERE worker_id = ? AND running = 1", (worker_id,)).fetchall()
        return {"concurrency": settings.APPLE_MUSIC_UPLOAD_CONCURRENCY, "jobs": [dict(row) for row in rows]}

    def settled(self, job_id, worker_id, lease):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            if not row or row["worker_id"] != worker_id or not secrets.compare_digest(row["lease_token"] or "", lease):
                raise UploadConflict("任务租约已变化")
            if row["state"] not in TERMINAL_STATES:
                raise UploadConflict("请先保存任务结束状态")
            connection.execute("UPDATE apple_uploads SET running = 0 WHERE id = ?", (job_id,))
        return {"settled": True}

    def cancel(self, job_id):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM apple_uploads WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise KeyError("上传任务不存在")
            if row["state"] != "queued" or row["lease_token"]:
                raise UploadConflict("只能取消尚未领取的任务；已发送请求的任务必须先核对本地记录")
            now = time.time()
            self.record_timing(connection, row, {"state": "cancelled"}, now, terminal=True)
            connection.execute("UPDATE apple_uploads SET state = 'cancelled', updated_at = ? WHERE id = ?", (now, job_id))
        return self.get(job_id)


apple_music_upload_service = AppleMusicUploadService()
