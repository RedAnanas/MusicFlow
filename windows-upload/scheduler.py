"""单调度器管理独立单曲进程；确认退出后才归还并发名额。"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from runtime import PRIVATE
from worker import recovery_action


TERMINAL = {"cloud_completed", "requires_review", "failed", "cancelled", "media_completed_extras_pending", "stopped"}


def stalled(monitor, now):
    """计算三分钟无进展、其他阶段两分钟；云端累计等待十分钟。"""
    if monitor.get("stage") == "session-wait":
        return False
    if now < monitor.get("wait_until", 0) + 30:
        return False
    if monitor.get("stage") in {"waiting", "extras-waiting"} and monitor.get("wait_seconds", 0) >= 600:
        return True
    limit = 180 if monitor.get("stage") in {"signature", "partial", "full-lowres", "decode", "media", "hash"} else 120
    return now - monitor.get("last_progress_at", now) > limit


def interrupted_result(worker, job, reason):
    """只读取检查点；不发送 Apple 请求，不凭进程退出推断请求失败。"""
    try:
        path = PRIVATE / f"{job['id']}.dpapi"
        saved = worker.load(path) if path.exists() else {}
        if saved.get("attempt", 0) == job["attempt"] and saved.get("final_event"):
            final = saved["final_event"]
            if reason == "stalled" and final["state"] in {"stopped", "failed"}:
                final = {**final, "error_code": reason}
            return final, saved
        record_path = PRIVATE / f"upload-{job['sha256']}.dpapi"
        record = worker.load(record_path) if record_path.exists() else None
        extras_path = PRIVATE / f"asset-upload-{job['sha256']}.dpapi"
        extras = worker.load(extras_path) if extras_path.exists() else {}
        if record and record.get("completed") and record.get("complete_received") and extras.get("completed"):
            return {"state": "cloud_completed", "stage": "complete", "action": "report_completed",
                    "evidence": {key: True for key in ("complete_received", "all_work_completed", "extras_completed")}}, saved
        uncertain = (not saved or saved.get("records_missing") or saved.get("asset_uncertain")
                     or (record is None and saved.get("request_started", saved.get("apple_started", False)))
                     or any(item.get("state") != "received" for item in extras.get("requests", [])))
        action = recovery_action(record, uncertain)
        return {"state": "requires_review" if action is None else "stopped" if job["stop_requested"] or reason == "stalled" else "failed",
                "action": action or "report_completed", "error_code": "request_uncertain" if action is None else reason}, saved
    except Exception:
        return {"state": "requires_review", "action": "report_completed", "error_code": "request_uncertain"}, {}


class UploadScheduler:
    POLL_SECONDS = 2
    STOP_GRACE_SECONDS = 45

    def __init__(self, worker, lock):
        self.worker, self.lock = worker, lock
        self.processes = {}
        self.blocked = False
        self.ready = None
        self.readiness_checked_at = 0

    def readiness(self):
        if self.ready is None or time.monotonic() - self.readiness_checked_at >= 10:
            self.ready = self.worker.readiness()
            self.readiness_checked_at = time.monotonic()
        return self.ready

    def spawn(self, job):
        job_id = job["job_id"]
        (PRIVATE / f"{job_id}.stop").unlink(missing_ok=True)
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("upload_task.py")), "--parent", str(os.getpid()),
             "--ffmpeg", str(self.worker.ffmpeg), "--target", str(self.worker.target)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, pass_fds=(self.lock.fileno(),))
        self.processes[job_id] = {"process": process, "stop_at": None, "reason": "worker_interrupted", "started_at": time.time()}
        try:
            process.stdin.write(json.dumps(job).encode())
        finally:
            process.stdin.close()

    @staticmethod
    def terminate(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)

    def finish(self, job, reason):
        prefix = f"/api/apple-music/uploads/{job['id']}"
        final, saved = interrupted_result(self.worker, job, reason)
        if job["state"] not in TERMINAL:
            self.worker.json_request(prefix + "/events", {**final, "lease_token": job["lease_token"], "sequence": job["sequence"] + 1})
        if saved.get("server_verified_at"):
            self.worker.server_verified_at = max(self.worker.server_verified_at or 0, saved["server_verified_at"])
        if saved.get("rejected_authorization_mtime"):
            self.worker.rejected_authorization_mtime = saved["rejected_authorization_mtime"]
            self.ready = None
        self.worker.save_state()
        (PRIVATE / f"{job['id']}.stop").unlink(missing_ok=True)
        self.worker.json_request(prefix + "/settled", {"lease_token": job["lease_token"]})

    def tick(self):
        ready = self.readiness()
        control = self.worker.json_request("/api/apple-music/workers/control", {
            **ready, "scheduler_error": "process_start_failed" if self.blocked else None})
        jobs = {job["id"]: job for job in control["jobs"]}
        for job_id, entry in list(self.processes.items()):
            if job_id not in jobs:
                self.terminate(entry["process"])
                del self.processes[job_id]
        for job_id, job in jobs.items():
            entry = self.processes.get(job_id)
            if entry is None:
                # 全局锁由任务继承；能启动新调度器就代表旧任务进程均已退出。
                self.finish(job, "worker_interrupted")
                continue
            process = entry["process"]
            if process.poll() is not None:
                self.terminate(process)
                self.finish(job, entry["reason"])
                del self.processes[job_id]
                continue
            try:
                saved = self.worker.load(PRIVATE / f"{job_id}.dpapi")
                monitor = saved.get("monitor") or {"last_progress_at": entry["started_at"]}
            except Exception:
                monitor = {"last_progress_at": entry["started_at"]}
            if not job["stop_requested"] and stalled(monitor, time.time()):
                entry["reason"] = "stalled"
            if job["stop_requested"] or entry["reason"] == "stalled":
                if entry["stop_at"] is None:
                    (PRIVATE / f"{job_id}.stop").touch(mode=0o600)
                    entry["stop_at"] = time.monotonic()
                elif time.monotonic() - entry["stop_at"] >= self.STOP_GRACE_SECONDS:
                    self.terminate(process)
        if (PRIVATE / ".pause-for-authorization").exists():
            return not self.processes
        if self.blocked:
            return False
        ready = self.readiness()
        if all(ready.get(key) for key in ("authorization_saved", "client_exited", "compatible", "context_matches")):
            while len(self.processes) < control["concurrency"]:
                if (PRIVATE / ".pause-for-authorization").exists():
                    break
                result = self.worker.json_request("/api/apple-music/workers/claim", {
                    "account_scope": self.worker.binding["account_scope"], "protocol_version": 2, "readiness": ready})
                if not result.get("job"):
                    break
                try:
                    self.spawn(result["job"])
                except Exception:
                    self.blocked = True
                    print("上传任务进程启动失败，已暂停补领；请检查系统资源后重启执行器。", flush=True)
                    break
        return False

    def run(self):
        try:
            while True:
                try:
                    if self.tick():
                        return
                except Exception:
                    print("上传调度器等待连接或记录恢复；未重新创建 Apple 上传请求。", flush=True)
                time.sleep(self.POLL_SECONDS)
        finally:
            for entry in self.processes.values():
                self.terminate(entry["process"])
