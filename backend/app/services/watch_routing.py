"""在音频进入监控目录前保存目标，重扫和重启沿用同一处理记录。"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import settings


def target_library(target):
    return target.library or ("nas" if target.type.value == "copy" else "apple")


class WatchRoutingService:
    def __init__(self, database_path=None):
        self.database_path = database_path or Path(settings.DATA_DIR) / "musicflow.db"

    @contextmanager
    def _connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.execute("""CREATE TABLE IF NOT EXISTS watch_file_routes (
            folder_id TEXT NOT NULL, path TEXT NOT NULL, size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (folder_id, path, size, mtime_ns))""")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _key(folder_id, path, signature_path=None):
        stat = Path(signature_path or path).stat()
        return folder_id, os.path.normcase(str(Path(path).resolve())), stat.st_size, stat.st_mtime_ns

    def get(self, folder_id, path):
        key = self._key(folder_id, path)
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM watch_file_routes WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", key).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _merge_outputs(previous, incoming):
        outputs = {tuple(item.get(field) for field in ("type", "library", "profile_id", "output_dir")): item for item in previous}
        outputs.update({tuple(item.get(field) for field in ("type", "library", "profile_id", "output_dir")): item for item in incoming})
        return list(outputs.values())

    def register(self, folder, path, signature_path, nas, apple, *, review=None, replace=False, merge=False, job_id=None, publish=None):
        key = self._key(folder.id, path, signature_path)
        data = {"path": str(path), "nas": nas, "apple": apple, "review": review, "created_at": time.time(), "outputs": [
            {**target.model_dump(mode="json"), "library": target_library(target), "state": "waiting"}
            for target in folder.targets
            if (nas if target_library(target) == "nas" else apple)
        ]}
        data["job_ids"] = [job_id] if job_id else []
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT data FROM watch_file_routes WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", key).fetchone()
            previous_data = json.loads(row[0]) if row else None
            if previous_data:
                data["job_ids"] = list(dict.fromkeys(previous_data.get("job_ids", []) + data["job_ids"]))
            if merge and previous_data:
                data.update(outputs=self._merge_outputs(data["outputs"], previous_data["outputs"]),
                            nas=nas or previous_data["nas"], apple=apple or previous_data["apple"],
                            created_at=previous_data["created_at"], review=previous_data["review"])
            if replace:
                # 手动补齐保留已经提交的输出，不重复转换或上传。
                previous = previous_data["outputs"] if previous_data else []
                for index, item in enumerate(data["outputs"]):
                    done = next((old for old in previous if all(old.get(field) == item.get(field) for field in ("type", "library", "profile_id", "output_dir")) and old["state"] != "waiting"), None)
                    if done and done["state"] in {"success", "submitted", "skipped"}:
                        data["outputs"][index] = done
            if replace or merge:
                connection.execute("DELETE FROM watch_file_routes WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", key)
            connection.execute("INSERT OR IGNORE INTO watch_file_routes VALUES (?, ?, ?, ?, ?)", (*key, json.dumps(data, ensure_ascii=False)))
            if publish:
                # 文件可见时路由事务尚持有写锁，监控读取会等到关联提交完成。
                publish()
            saved = connection.execute("SELECT data FROM watch_file_routes WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", key).fetchone()
        return json.loads(saved[0])

    def save(self, folder_id, path, data):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            key = self._key(folder_id, path)
            row = connection.execute("SELECT data FROM watch_file_routes WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", key).fetchone()
            if row:
                latest = json.loads(row[0])
                fields = ("type", "library", "profile_id", "output_dir")
                keys = {tuple(item.get(field) for field in fields) for item in latest["outputs"]}
                updates = [item for item in data["outputs"] if tuple(item.get(field) for field in fields) in keys]
                data = {**latest, "outputs": self._merge_outputs(latest["outputs"], updates),
                        "job_ids": list(dict.fromkeys(latest.get("job_ids", []) + data.get("job_ids", [])))}
            connection.execute("UPDATE watch_file_routes SET data=? WHERE folder_id=? AND path=? AND size=? AND mtime_ns=?", (json.dumps(data, ensure_ascii=False), *key))

    def list_files(self, folder_id):
        with self._connect() as connection:
            rows = connection.execute("SELECT data FROM watch_file_routes WHERE folder_id=? ORDER BY rowid DESC LIMIT 200", (folder_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def for_source(self, path):
        if not path or not Path(path).is_file():
            return None
        key = self._key("", path)
        with self._connect() as connection:
            row = connection.execute("SELECT folder_id, data FROM watch_file_routes WHERE path=? AND size=? AND mtime_ns=? ORDER BY rowid DESC LIMIT 1", key[1:]).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    @staticmethod
    def output_status(item):
        from app.api.routes.tasks import tasks_cache
        task = tasks_cache.get(item.get("task_id"))
        if not task:
            return "requires_review" if item.get("task_id") else item["state"]
        if task.status.value in {"failed", "cancelled"}:
            return "failed"
        if task.status.value != "success":
            return "processing"
        if item["library"] == "nas":
            return "success"
        if task.apple_music_delivery_mode == "direct_upload":
            from app.services.apple_music_upload import apple_music_upload_service
            upload = apple_music_upload_service.for_task(task.id)
            return upload["state"] if upload else "submitted"
        if task.apple_music_status == "failed":
            return "failed"
        if task.apple_music_status == "received":
            return "received_unverified"
        if task.apple_music_status == "waiting":
            return "handoff_pending"
        return "submitted"

    def plan(self, folder, path):
        existing = self.get(folder.id, path)
        if existing:
            return existing
        from app.core import metadata_service
        from app.services.media_library_service import media_library_service
        from app.services.dual_library_service import dual_library_service, normalize_text

        track = metadata_service.read_metadata(str(path)) or {}
        nas = folder.default_target in {"nas", "both"}
        apple = folder.default_target in {"apple", "both"}
        if not track.get("title") or not track.get("artist"):
            return self.register(folder, path, path, nas, apple, review="缺少歌名或歌手，请选择目标并确认处理")
        local = media_library_service.load_tracks(False)
        presence = dual_library_service.lookup_presence(track, dual_library_service.build_presence_index(local))
        nas = nas and not presence["nas_present"]
        apple = apple and not presence["apple_present"]
        uncertain_local = nas and any(
            normalize_text(item.get("title")) == normalize_text(track.get("title"))
            and normalize_text(item.get("artist")) == normalize_text(track.get("artist")) for item in local
        )
        review = "存在相似曲目，请核对版本后选择目标" if uncertain_local or (apple and dual_library_service.find_apple_candidates(track)) else None
        return self.register(folder, path, path, nas, apple, review=review)


watch_routing = WatchRoutingService()
