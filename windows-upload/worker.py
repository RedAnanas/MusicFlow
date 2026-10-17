"""主动领取 MusicFlow 成品，串行执行所在服务端的独立上传。"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from runtime import PRIVATE, exclusive_lock

AUTHORIZATION_FILE = "apple-client-authorization.dpapi" if os.name == "nt" else "account.mfup"


class WorkerError(Exception):
    """对外仅返回错误类别，不包含远端响应、账号或令牌。"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise WorkerError("MusicFlow 地址必须是无账号、参数和子路径的 HTTP(S) 地址")
    return url.rstrip("/")


def identity(bundle):
    account, context = bundle["account"], bundle["context"]
    fields = [account["headers"]["X-Dsid"], context["common"]["cuid"], context["common"]["troveid"], context["persistent-library-id"]]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def recovery_action(record, asset_uncertain=False):
    """仅根据持久证据选择恢复入口，不把网络超时当成尚未提交。"""
    if asset_uncertain:
        return None
    if record is None:
        return "upload"
    if record.get("completed") and record.get("complete_received"):
        return "upload_media_extras"
    requests = record.get("requests", [])
    if not requests or requests[-1].get("state") != "received":
        return None
    if record.get("cloud_id") and record.get("status") and requests[-1].get("route") in {"downloadRequests", "uploadResponses"}:
        return "resume_work"
    if len(requests) >= 2 and requests[1].get("route") == "updateLibrary" and requests[1].get("state") == "received" and not record.get("cloud_id"):
        return "resume_pending"
    return None


def checksum(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class Worker:
    HEARTBEAT_SECONDS = 15

    def __init__(self, binding, ffmpeg, target):
        from prototype.local_session import load_session, save_session
        from prototype import windows_sap

        self.load, self.save = load_session, save_session
        self.binding, self.ffmpeg = binding, ffmpeg
        self.url = validate_url(binding["url"])
        windows_sap.TARGET = target
        self.target = target
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        state_path = PRIVATE / "worker-state.dpapi"
        state = self.load(state_path) if state_path.exists() else {}
        self.server_verified_at = state.get("server_verified_at")
        self.rejected_authorization_mtime = state.get("rejected_authorization_mtime")

    def save_state(self):
        self.save(PRIVATE / "worker-state.dpapi", {"server_verified_at": self.server_verified_at,
                  "rejected_authorization_mtime": self.rejected_authorization_mtime})

    def request(self, path, data=None, lease=None):
        if not path.startswith("/api/apple-music/") or path.startswith("//"):
            raise WorkerError("不允许的后端接口")
        headers = {"Authorization": "Bearer " + self.binding["token"], "X-Worker-Id": self.binding["worker_id"]}
        if lease:
            headers["X-Upload-Lease"] = lease
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        return self.opener.open(request, timeout=30)

    def json_request(self, path, data):
        with self.request(path, data) as response:
            return json.loads(response.read(1024 * 1024))

    def readiness(self):
        from prototype.windows_sap import EXPECTED, CORE_FP_HASH

        exited = (subprocess.run(["powershell.exe", "-NoProfile", "-Command",
            "@(Get-Process AppleMusic,AMPLibraryAgent -ErrorAction SilentlyContinue).Count"], capture_output=True, check=True).stdout.strip() == b"0") if os.name == "nt" else True
        compatible = (self.target.is_file() and self.target.with_name("CoreFP.dll").is_file()
                      and checksum(self.target) == EXPECTED and checksum(self.target.with_name("CoreFP.dll")) == CORE_FP_HASH)
        if os.name != "nt" and compatible:
            from prototype.windows_sap import SDK_IMAGES
            compatible = all(self.target.with_name(name).is_file() and checksum(self.target.with_name(name)) == digest
                             for name, (_, digest) in SDK_IMAGES.items())
        authorization_saved = (PRIVATE / AUTHORIZATION_FILE).is_file()
        matches = False
        if authorization_saved:
            bundle_path = PRIVATE / AUTHORIZATION_FILE
            if bundle_path.stat().st_mtime_ns == self.rejected_authorization_mtime:
                return {"authorization_saved": False, "client_exited": exited, "compatible": compatible, "context_matches": False,
                        "server_verified_at": self.server_verified_at}
            bundle = self.load(bundle_path)
            current = identity(bundle)
            binding_file = PRIVATE / "library-binding.dpapi"
            if binding_file.exists():
                saved = self.load(binding_file)
                matches = saved == {"account_scope": self.binding["account_scope"], "identity": current}
            else:
                self.save(binding_file, {"account_scope": self.binding["account_scope"], "identity": current})
                matches = True
        return {"authorization_saved": authorization_saved, "client_exited": exited, "compatible": compatible,
                "context_matches": matches, "server_verified_at": self.server_verified_at}

    def download(self, job, progress=None):
        path = PRIVATE / (job["job_id"] + ".m4a")
        if path.exists() and path.stat().st_size == job["size"] and checksum(path) == job["sha256"]:
            return path
        part = path.with_suffix(".part")
        try:
            with self.request(job["content_url"], lease=job["lease_token"]) as response, part.open("wb") as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > job["size"]:
                        raise WorkerError("成品大小超过登记值")
                    output.write(chunk)
                    if progress:
                        progress("download", {"bytes_sent": total, "bytes_total": job["size"]})
            if part.stat().st_size != job["size"] or checksum(part) != job["sha256"]:
                raise WorkerError("成品完整性校验失败")
            part.replace(path)
            return path
        finally:
            part.unlink(missing_ok=True)

    def execute(self, job):
        from prototype.uploader import WindowsSongUploader
        from prototype import uploader as uploader_module, extra_asset_upload

        job_id = str(__import__("uuid").UUID(job["job_id"]))
        if not re.fullmatch(r"[0-9a-f]{64}", job["sha256"]) or not isinstance(job["size"], int) or job["size"] <= 0:
            raise WorkerError("成品登记信息无效")
        if job["content_url"] != f"/api/apple-music/uploads/{job_id}/content":
            raise WorkerError("成品接口与任务不一致")
        local = PRIVATE / (job_id + ".dpapi")
        saved = self.load(local) if local.exists() else {"sha256": job["sha256"], "account_scope": self.binding["account_scope"],
                                                       "records_missing": job.get("recovery_required", False)}
        if saved["sha256"] != job["sha256"] or saved["account_scope"] != self.binding["account_scope"]:
            raise WorkerError("本地任务与领取任务不一致")
        # 新租约从序号零开始；本地完成结果跨租约保留，优先重报。
        if saved.get("attempt", 0) != job["attempt"]:
            saved.pop("final_event", None)
            saved.pop("reported", None)
        previously_started = saved.get("apple_started", False)
        saved.update(lease_token=job["lease_token"], sequence=0, attempt=job["attempt"])
        self.save(local, saved)
        event_path = f"/api/apple-music/uploads/{job_id}/events"
        stop = threading.Event()
        lost = threading.Event()
        event_lock = threading.RLock()
        current = {"state": "staging", "stage": "download", "action": job["action"], "stage_token": time.time()}
        signature_started = None
        pending = None
        last_progress_sent = 0.0
        original_upload_asset = uploader_module.upload_asset

        def guarded_asset(*args, **kwargs):
            with event_lock:
                saved["asset_uncertain"] = True
                self.save(local, saved)
            kwargs["progress"] = lambda sent, total: progress("asset-bytes", {"bytes_sent": sent, "bytes_total": total})
            result = original_upload_asset(*args, **kwargs)
            with event_lock:
                saved["asset_uncertain"] = False
                self.save(local, saved)
            return result

        uploader_module.upload_asset = guarded_asset
        extra_asset_upload.upload_asset = guarded_asset

        def inspect_records():
            try:
                record_path = PRIVATE / f"upload-{job['sha256']}.dpapi"
                record = self.load(record_path) if record_path.exists() else None
                extras_path = PRIVATE / f"asset-upload-{job['sha256']}.dpapi"
                extras = self.load(extras_path) if extras_path.exists() else {}
                uncertain = (saved.get("records_missing", False) or saved.get("asset_uncertain", False)
                             or (record is None and (saved.get("apple_started", False) or extras_path.exists()))
                             or any(item.get("state") != "received" for item in extras.get("requests", [])))
                return record, recovery_action(record, uncertain)
            except Exception:
                return {}, None

        def send(changes=None):
            nonlocal pending
            with event_lock:
                if pending is not None:
                    self.json_request(event_path, pending)
                    saved["sequence"] = pending["sequence"]
                    pending = None
                if changes:
                    next_stage = changes.get("stage", current.get("stage"))
                    new_step = changes.pop("new_step", False)
                    if next_stage != current.get("stage") or new_step:
                        current.update(stage_token=max(time.time(), current.get("stage_token", 0) + 0.000001), stage_progress=None, wait_seconds=None, bytes_sent=None, bytes_total=None)
                    current.update(changes)
                if signature_started is not None and current.get("stage") == "signature" and current.get("signature_progress", 0) < 100:
                    current["signature_elapsed_seconds"] = round(time.monotonic() - signature_started, 1)
                pending = {**current, "sequence": saved["sequence"] + 1, "lease_token": job["lease_token"]}
                self.json_request(event_path, pending)
                saved["sequence"] = pending["sequence"]
                pending = None
                self.save(local, saved)

        def heartbeat():
            while not stop.wait(self.HEARTBEAT_SECONDS):
                try:
                    send()
                except HTTPError as exc:
                    if exc.code in {401, 403, 409}:
                        lost.set()
                        return
                except Exception:
                    pass

        def progress(stage, value=None):
            nonlocal signature_started, last_progress_sent
            if lost.is_set():
                raise WorkerError("任务租约已失效")
            stages = {"prepare-fingerprint": "processing", "get-fingerprint": "processing", "upload-fingerprint": "fingerprint-upload", "signature": "signature",
                      "hash-track": "hash", "prepare-track": "prepare-track", "media": "media", "decode": "decode",
                      "partial": "partial", "full-lowres": "full-lowres", "download": "download",
                      "upload-track": "audio", "create-session": "metadata", "check-session": "processing",
                      "metadata-processing": "waiting", "waiting": "waiting", "complete": "processing"}
            changes = {"state": "cloud_processing" if stage in {"waiting", "metadata-processing"} else "uploading",
                       "stage": "extras" if stage.startswith("extras-") or stage in {"upload-artwork", "upload-lyrics"} else stages.get(stage, "processing")}
            if stage == "extras-waiting":
                changes.update(state="cloud_processing", stage="extras-waiting")
            if stage == "asset-bytes":
                changes = {"stage": current.get("stage")}
            if stage == "download":
                changes["state"] = "staging"
            if isinstance(value, dict):
                changes.update(value)
                total = value.get("bytes_total", 0)
                if total:
                    changes["stage_progress"] = min(100, value["bytes_sent"] / total * 100)
            elif stage in {"waiting", "metadata-processing", "extras-waiting"}:
                changes.update(wait_seconds=value, new_step=True)
            elif type(value) is int and stage in {"signature", "partial", "full-lowres"}:
                changes["stage_progress"] = value
            if stage == "signature" and type(value) is int and 0 <= value <= 100:
                if signature_started is None:
                    signature_started = time.monotonic()
                changes.update(signature_progress=value, signature_elapsed_seconds=round(time.monotonic() - signature_started, 1))
            with event_lock:
                if changes.get("stage") == current.get("stage") and value is not None and not changes.get("new_step") and changes.get("stage_progress") != 100 and time.monotonic() - last_progress_sent < 1:
                    current.update(changes)
                    return
                send(changes)
                last_progress_sent = time.monotonic()

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if saved.get("final_event"):
                saved["final_sequence"] = 1
                self.save(local, saved)
                send(saved["final_event"])
                saved["reported"] = True
                self.save(local, saved)
                return
            send()
            source = self.download(job, progress)
            send({"state": "validating", "stage": "validation"})
            ready = self.readiness()
            if not all(ready[key] for key in ("authorization_saved", "client_exited", "compatible", "context_matches")):
                raise WorkerError("上传前本机就绪状态发生变化")
            bundle = PRIVATE / AUTHORIZATION_FILE
            uploader = WindowsSongUploader(bundle, bundle, PRIVATE, self.ffmpeg, progress)
            record, action = inspect_records()
            if action is None:
                final = {"state": "requires_review", "error_code": "request_uncertain"}
            else:
                with event_lock:
                    saved["apple_started"] = True
                    self.save(local, saved)
                result = getattr(uploader, action)(source)
                record = self.load(PRIVATE / f"upload-{job['sha256']}.dpapi")
                complete = bool(record.get("completed") and record.get("complete_received") and result.get("extras_completed"))
                if not complete:
                    raise WorkerError("缺少完整上传完成证据")
                saved["asset_uncertain"] = False
                self.server_verified_at = time.time()
                self.save_state()
                final = {"state": "cloud_completed", "stage": "complete", "action": "report_completed",
                         "evidence": {"complete_received": True, "all_work_completed": True, "extras_completed": True}}
        except Exception as exc:
            if isinstance(exc, HTTPError) and exc.code in {401, 403} and urlsplit(exc.url).netloc != urlsplit(self.url).netloc:
                self.rejected_authorization_mtime = (PRIVATE / AUTHORIZATION_FILE).stat().st_mtime_ns
                self.save_state()
            record, action = inspect_records()
            message = str(exc)
            code = ("unsupported_fingerprint" if any(word in message for word in ("指纹", "工作任务")) else
                    "unsupported_media" if "AAC LC" in message else
                    "incompatible_version" if "版本" in message else
                    "context_mismatch" if "资料库" in message else
                    "authorization_required" if isinstance(exc, HTTPError) and exc.code in {401, 403} else
                    "content_changed" if isinstance(exc, WorkerError) and "成品" in message else "upload_failed")
            state = "requires_review" if action is None else "media_completed_extras_pending" if record and record.get("completed") else "failed"
            # 未产生任何 Apple 请求的明确校验失败可以重试原成品。
            if record is None and not previously_started and not saved.get("records_missing") and not saved.get("asset_uncertain"):
                state, action = "failed", "upload"
                saved["apple_started"] = False
            if state == "requires_review":
                code = "request_uncertain" if code == "upload_failed" else code
            final = {"state": state, "error_code": code, "action": action or "upload"}
        finally:
            stop.set()
            thread.join(timeout=35)
            uploader_module.upload_asset = original_upload_asset
            extra_asset_upload.upload_asset = original_upload_asset
        saved["final_event"] = final
        saved["final_sequence"] = saved["sequence"] + 1
        saved["reported"] = False
        self.save(local, saved)
        send(final)
        saved["reported"] = True
        self.save(local, saved)
        print(json.dumps({"job_id": job_id, "state": final["state"], "error_code": final.get("error_code")}, ensure_ascii=False), flush=True)

    def report_saved_results(self):
        """启动时先重报本地终态；过期租约仍须由后端重新领取。"""
        for path in PRIVATE.glob("*.dpapi"):
            if not re.fullmatch(r"[0-9a-f-]{36}", path.stem):
                continue
            saved = self.load(path)
            if saved.get("reported") or not saved.get("final_event") or saved.get("account_scope") != self.binding["account_scope"]:
                continue
            try:
                self.json_request(f"/api/apple-music/uploads/{path.stem}/events", {
                    **saved["final_event"], "lease_token": saved["lease_token"], "sequence": saved.get("final_sequence", saved["sequence"] + 1)})
            except Exception:
                continue
            saved["reported"] = True
            self.save(path, saved)

    def run(self):
        self.report_saved_results()
        while True:
            if os.name != "nt" and (PRIVATE / ".pause-for-authorization").exists():
                return
            try:
                result = self.json_request("/api/apple-music/workers/claim", {
                    "account_scope": self.binding["account_scope"], "protocol_version": 1, "readiness": self.readiness()})
                if result.get("job"):
                    self.execute(result["job"])
                else:
                    time.sleep(10)
            except KeyboardInterrupt:
                return
            except Exception:
                print("工作进程等待连接或本机状态恢复；未重新创建 Apple 上传请求。", flush=True)
                time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-binding", type=Path, help="导入后端生成的临时绑定文件，完成后删除原文件")
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--target", type=Path, help="合法安装的指定版本 AMPLibraryAgent.exe，其目录必须有 CoreFP.dll")
    args = parser.parse_args()
    from prototype.local_session import load_session, save_session

    with exclusive_lock():
        binding_path = PRIVATE / "musicflow-binding.dpapi"
        if args.import_binding:
            if binding_path.exists():
                parser.error("已有绑定，请保留原文件；首版不自动替换账号或后端")
            binding = json.loads(args.import_binding.read_text(encoding="utf-8-sig"))
            validate_url(binding["url"])
            save_session(binding_path, binding)
            print("工作进程绑定已加密保存；请删除临时绑定文件。")
            return
        probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        if not args.ffmpeg or not args.ffmpeg.is_file() or not args.ffmpeg.with_name(probe_name).is_file() or not args.target:
            parser.error("请指定 --ffmpeg 和 --target，并确认同目录 ffprobe 可用")
        Worker(load_session(binding_path), args.ffmpeg, args.target).run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("工作进程未启动，请检查本机绑定、依赖及授权；敏感错误信息未输出。")
        raise SystemExit(1) from None
