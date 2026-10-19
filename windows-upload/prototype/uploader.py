"""Windows 独立 M4A 上传入口；账号首次授权和资料库上下文保存在 DPAPI 中。"""

import base64
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, build_opener

from prototype.audio_asset import m4a_audio_data
from prototype.audio_signature import generate_signature
from prototype.legacy_fingerprint import generate_fingerprint
from prototype import windows_sap
from prototype.control_request import build_control_request
from prototype.incremental_metadata import single_track_payload
from prototype.local_session import load_session, request_headers, save_session
from prototype.media_extras import extract_media_extras
from prototype.upload_asset import upload_asset
from prototype.windows_sap import WindowsSapSigner, NoRedirect


class SongUploadError(Exception):
    """对外错误不包含认证头、云标识或工作票据。"""


class UploadSessionChanged(SongUploadError):
    """云端返回其他会话时保留原检查点，不继续处理该响应。"""

    code = "session_changed"


class WindowsSongUploader:
    """单线程单曲上传；保留每次请求的受保护记录，避免自动重复新增歌曲。"""

    def __init__(self, account_path, context_path, private_directory, ffmpeg, progress=None):
        account = load_session(account_path)
        context = account if Path(account_path).resolve() == Path(context_path).resolve() else load_session(context_path)
        self.account = account.get("account", account)
        self.context = context.get("context", context)
        self.private = Path(private_directory)
        self.ffmpeg = Path(ffmpeg)
        self.ffprobe = self.ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        self.progress = progress or (lambda stage, value=None: None)
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _post(self, endpoint, payload, route=None, signed=True):
        self.progress("create-session" if route == "updateLibrary" else "protocol")
        request = build_control_request(endpoint, payload,
                    request_headers(self.account, endpoint, self.common["cuid"]),
                    self.signer if signed else None, server_route=route)
        record = {"state": "prepared", "request": base64.b64encode(request.data).decode("ascii"), "route": route,
                  "started_at": time.time()}
        started = time.monotonic()
        self.state["requests"].append(record)
        save_session(self.job, self.state)
        try:
            with self.opener.open(request, timeout=45) as response:
                raw = response.read(1048577)
                encoding = response.headers.get("Content-Encoding", "").lower()
                record["http_status"] = response.status
        finally:
            record.update(ended_at=time.time(), elapsed_seconds=time.monotonic() - started)
            save_session(self.job, self.state)
        if len(raw) > 1048576:
            raise SongUploadError("上传控制响应超过支持范围")
        record.update(state="received", response=base64.b64encode(raw).decode("ascii"),
                      ended_at=time.time(), elapsed_seconds=time.monotonic() - started)
        save_session(self.job, self.state)
        if encoding == "gzip" or raw.startswith(b"\x1f\x8b\x08"):
            raw = gzip.decompress(raw)
        if len(raw) > 1048576:
            raise SongUploadError("上传控制响应解压后超过支持范围")
        parsed = plistlib.loads(raw)
        if not isinstance(parsed, dict) or parsed.get("status") != 0:
            raise SongUploadError("上传服务未接受当前协议步骤")
        return parsed

    def _check_job_context(self, state):
        """刷新客户端授权后，不能拿其他资料库的旧任务继续处理。"""
        record = next((r for r in state.get("requests", []) if r.get("route") == "updateLibrary"), None)
        if record is None:
            raise SongUploadError("旧上传记录缺少可核对的资料库身份")
        raw = base64.b64decode(record["request"])
        metadata = plistlib.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b\x08") else raw)
        expected = {key: self.context["common"][key] for key in ("cuid", "troveid")}
        expected["persistent-library-id"] = self.context["persistent-library-id"]
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise SongUploadError("当前授权与旧任务不属于同一资料库，停止恢复或补传")

    def _media(self, source, directory):
        self.progress("media")
        probe = subprocess.run([str(self.ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
                               capture_output=True, check=True)
        info = json.loads(probe.stdout)
        audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        if len(audio) != 1 or audio[0].get("codec_name") != "aac" or audio[0].get("profile") != "LC":
            raise SongUploadError("当前上传入口只验证了单音轨 AAC LC 的 M4A")
        stream = audio[0]
        self.audio = m4a_audio_data(source.read_bytes())
        self.clean = directory / "clean.m4a"
        result = subprocess.run([str(self.ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                                "-map", "0:a:0", "-vn", "-c:a", "copy", "-map_metadata", "-1", "-movflags", "+faststart", str(self.clean)],
                               capture_output=True)
        if result.returncode or m4a_audio_data(self.clean.read_bytes()) != self.audio:
            raise SongUploadError("清理 M4A 后音频数据验证失败")
        self.signature = None
        self._fingerprints = {}
        self.source = source
        self.directory = directory
        self.extras = extract_media_extras(source, info, self.ffmpeg, directory)
        tags = {key.casefold(): value for key, value in info.get("format", {}).get("tags", {}).items()}
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        track = {"persistent-id": secrets.token_hex(8).upper(), "item-name": tags.get("title") or source.stem,
                 "kind": "song", "format": "m4a", "item-checked": True, "size": source.stat().st_size,
                 "duration": round(float(stream["duration"]) * 1000), "sample-rate": float(stream["sample_rate"]),
                 "bit-rate": round(int(stream["bit_rate"]) / 1000), "audio-codec": 1836069985, "audio-codec-sub-type": 2,
                 "valid-fields": 255, "cddb-fingerprint-not-avail": True, "lacks-cover-art": self.extras["cover"] is None,
                 "added-date": now, "modified-date": now, "filename": source.name,
                 "match-id": secrets.randbits(63) or 1}
        # 匹配元数据与云资料库字段使用不同名称；官方请求同时携带两组。
        for tag, keys in (("artist", ("artist-name", "artist")),
                          ("album", ("playlist-name", "album")),
                          ("album_artist", ("playlist-artist-name", "album-artist")),
                          ("composer", ("composer-name", "composer")),
                          ("genre", ("genre-name",)), ("comment", ("comment",))):
            if tags.get(tag):
                for key in keys:
                    track[key] = tags[tag]
        year = re.match(r"^[0-9]{4}(?:$|[-/])", tags.get("date", tags.get("year", "")))
        if year:
            track["year"] = int(year.group()[:4])
        for tag, prefix in (("track", "track"), ("disc", "disc")):
            parts = tags.get(tag, "").split("/")
            if len(parts) <= 2:
                for value, suffix in zip(parts, ("number", "count")):
                    value = value.strip()
                    if value.isascii() and value.isdecimal() and int(value) > 0:
                        track[f"{prefix}-{suffix}"] = int(value)
        if self.extras["lyrics"]:
            track["has-lyrics"] = True
        return track

    def _signature(self):
        if self.signature is None:
            self.progress("decode")
            cache = self.private / "signature-cache"
            cache.mkdir(mode=0o700, exist_ok=True)
            if cache.is_symlink():
                raise SongUploadError("签名缓存目录不能为符号链接")
            pcm = self.directory / "signature.pcm"
            result = subprocess.run([str(self.ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.source),
                                    "-ac", "1", "-ar", "16000", "-f", "f32le", str(pcm)], capture_output=True)
            if result.returncode:
                raise SongUploadError("生成音频签名所需的 PCM 失败")
            samples = pcm.read_bytes()
            self.progress("signature", 0)
            # 使用实际解码样本，避免相同 AAC 载荷但不同裁剪信息误命中缓存。
            key = hashlib.sha256(b"signature-f32le-16k-mono-v1\0" + windows_sap.EXPECTED.encode() + samples).hexdigest()
            target = cache / (key + ".bin")
            if target.is_file() and not target.is_symlink() and 32 < target.stat().st_size <= 1048576 + 32:
                data = target.read_bytes()
                if hashlib.sha256(data[32:]).digest() == data[:32]:
                    self.signature = data[32:]
                    self.progress("signature", 100)
                    return self.signature
            self.signature = generate_signature(samples, self.progress)
            (self.directory / "signature.bin").write_bytes(self.signature)
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as output:
                temporary = Path(output.name)
                output.write(hashlib.sha256(self.signature).digest() + self.signature)
                output.flush()
                os.fsync(output.fileno())
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            self.progress("signature", 100)
        return self.signature

    def _fingerprint(self, kind):
        if kind == "signature":
            return self._signature()
        if kind not in ("partial", "full-lowres"):
            raise SongUploadError("服务端请求了尚未验证的指纹类型")
        cache = getattr(self, "_fingerprints", {})
        if kind not in cache:
            self.progress("decode")
            pcm = self.directory / "fingerprint.pcm"
            result = subprocess.run([str(self.ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.source),
                                     "-ac", "2", "-ar", "44100", "-f", "s16le", str(pcm)], capture_output=True)
            if result.returncode:
                raise SongUploadError("生成旧版指纹 PCM 失败")
            try:
                sdk = Path(os.environ.get("MUSICFLOW_APPLE_SDK_DIRECTORY", windows_sap.TARGET.parent))
                self.progress(kind)
                cache[kind] = generate_fingerprint(pcm, kind, sdk, self.progress)
            except (OSError, RuntimeError, windows_sap.SapError):
                raise SongUploadError("旧版指纹生成失败，请核对算法文件版本") from None
            self._fingerprints = cache
        return cache[kind]

    def upload_media_extras(self, source):
        """给已成功上传的同一首歌曲补传歌词和封面，不重新提交音频。"""
        from prototype.extra_asset_upload import upload_extras
        self.progress("extras-create-session")

        source = Path(source).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        original = load_session(self.private / f"upload-{digest}.dpapi")
        self._check_job_context(original)
        if not original.get("completed") or not original.get("cloud_id"):
            raise SongUploadError("没有该文件的成功上传记录，不能补传资产")
        directory = self.private / f"media-{digest}"
        directory.mkdir(parents=True, exist_ok=True)
        probe = subprocess.run([str(self.ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
                               capture_output=True, check=True)
        extras = extract_media_extras(source, json.loads(probe.stdout), self.ffmpeg, directory)
        assets = {}
        if extras["lyrics"]:
            assets["lyrics"] = extras["lyrics"].encode("utf-8")
        if extras["cover"]:
            assets["artwork"] = extras["cover"]["path"].read_bytes()
        if not assets:
            return {"extras_completed": True, "assets": []}
        if original.get("complete_action"):
            complete = plistlib.loads(base64.b64decode(original["complete_action"]))
            if not complete.get("error") and all(complete.get(f"token-{kind}") for kind in assets):
                return {"extras_completed": True, "assets": sorted(assets), "client_rpc_used": False}
        self.job = self.private / f"asset-upload-{digest}.dpapi"
        self.state = load_session(self.job) if self.job.exists() else {
            "version": 1, "source_sha256": digest, "cloud_id": original["cloud_id"],
            "requests": [], "completed": False}
        if self.state["cloud_id"] != original["cloud_id"]:
            raise SongUploadError("资产上传记录与当前云歌曲不一致")
        self.common = {key: self.context["common"][key] for key in ("cuid", "troveid")}
        self.common.update({"dsid": int(self.account["headers"]["X-Dsid"]),
                            "protocol-version": 1, "min-compatible-version": 1,
                            "itunes-version": "1.6.4.90", "itunes-platform": "Windows"})
        self.signer = WindowsSapSigner()
        return upload_extras(self, assets)

    def _action(self, action):
        reply = deepcopy(action)
        name = action["action"]
        self.progress(name)
        if name == "get-fingerprint":
            kind = action.get("fingerprint-type")
            if kind not in ("partial", "full-lowres"):
                raise SongUploadError("服务端请求了尚未验证的即时指纹类型")
            reply.update({"fingerprint-value": self._fingerprint(kind), "status": 0})
        elif name == "hash-track":
            for kind, asset in action["assets"].items():
                if asset != {"hash-type": "sha256"}:
                    raise SongUploadError("未验证的资产哈希任务")
                data = self._asset_data(kind)
                reply["assets"][kind].update({"hash-value": hashlib.sha256(data).hexdigest(), "status": 0})
        elif name == "prepare-fingerprint":
            if action.get("fingerprint-type") not in ("partial", "full-lowres", "signature") or action.get("hash-type") != "md5":
                raise SongUploadError("服务端请求了尚未实现的旧版音频指纹")
            data = self._fingerprint(action["fingerprint-type"])
            reply.update({"file-size": len(data), "hash-value": hashlib.md5(data).hexdigest(), "upload-type": "clean", "status": 0})
        elif name == "upload-fingerprint":
            if action.get("fingerprint-type") not in ("partial", "full-lowres", "signature"):
                raise SongUploadError("未验证的指纹资产任务")
            descriptor = reply.pop("upload-info")
            data = self._fingerprint(action["fingerprint-type"])
            self.progress("upload-fingerprint")
            started = time.monotonic()
            statuses = upload_asset(descriptor, data, self.account["headers"]["User-Agent"])
            reply.update({"response-code": statuses[-1], "upload-seconds": int(time.monotonic() - started)})
        elif name == "prepare-track":
            for kind, asset in action["assets"].items():
                expected = {"hash-type": "md5", "upload-type": "clean"} if kind == "audio" else {"hash-type": "md5"}
                if asset != expected:
                    raise SongUploadError("未验证的资产准备任务")
                data = self._asset_data(kind, clean_audio=True)
                reply["assets"][kind].update({"file-size": len(data), "hash-value": hashlib.md5(data).hexdigest(), "status": 0})
        elif name == "upload-track":
            for kind, asset in reply["assets"].items():
                self.progress("upload-track" if kind == "audio" else f"upload-{kind}")
                data = self._asset_data(kind, clean_audio=True)
                descriptor = asset.pop("upload-info")
                asset.pop("upload-type", None)
                started = time.monotonic()
                statuses = upload_asset(descriptor, data, self.account["headers"]["User-Agent"])
                asset.update({"response-code": statuses[-1], "upload-seconds": int(time.monotonic() - started)})
                if kind == "audio":
                    self.state["audio_uploaded"] = True
        elif name == "complete":
            if action.get("error"):
                raise SongUploadError("服务端未完成歌曲上传")
            self.state["complete_received"] = True
            self.state["complete_action"] = base64.b64encode(plistlib.dumps(action)).decode("ascii")
            return None
        else:
            raise SongUploadError("服务端请求了尚未实现的工作任务")
        return reply

    def _asset_data(self, kind, clean_audio=False):
        """哈希针对资产原字节，整首音频上传使用清理后的容器。"""
        if kind == "audio":
            return self.clean.read_bytes() if clean_audio else self.audio
        if kind == "lyrics" and self.extras.get("lyrics"):
            return self.extras["lyrics"].encode("utf-8")
        if kind == "artwork" and self.extras.get("cover"):
            return self.extras["cover"]["path"].read_bytes()
        raise SongUploadError("服务端请求了本地不存在或尚未实现的资产")

    def upload(self, source):
        """提交一首歌曲并等待 all-work-completed；重复文件需人工审查既有记录。"""
        source = Path(source).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.job = self.private / f"upload-{digest}.dpapi"
        if self.job.exists():
            raise SongUploadError("该文件已有上传记录，停止自动创建重复条目")
        directory = self.private / f"media-{digest}"
        directory.mkdir(parents=True, exist_ok=True)
        track = self._media(source, directory)
        self.common = {k: v for k, v in self.context["common"].items() if k not in ("num-tracks", "update-id")}
        self.common.update(incremental=True, **{"cloud-incremental-update": True, "auto-update": False})
        self.state = {"version": 1, "source_sha256": digest, "track_id": track["persistent-id"], "requests": [],
                      "audio_uploaded": False, "complete_received": False, "completed": False}
        self.signer = WindowsSapSigner()
        self.progress("create-session")
        initial = self._post(self.account["upload_configuration"]["cloud-library-update-request"], {**self.common, "num-tracks": 1})
        endpoint = initial["url"]
        query = parse_qs(urlsplit(endpoint).query)
        if any(query.get(key) != [self.common[key]] for key in ("cuid", "troveid")):
            raise SongUploadError("服务端更新会话与当前资料库不一致")
        self._post(endpoint, single_track_payload(self.context, self.common, track), "updateLibrary")
        return self._finish(initial, track["persistent-id"])

    def resume_pending(self, source):
        """仅恢复元数据已接受、尚未开始工作任务的会话，不重复创建歌曲。"""
        source = Path(source).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.job = self.private / f"upload-{digest}.dpapi"
        self.state = load_session(self.job)
        self._check_job_context(self.state)
        if self.state.get("completed") or "cloud_id" in self.state:
            raise SongUploadError("此记录不属于尚未开始工作任务的等待会话")
        records = self.state["requests"]
        if (len(records) < 2 or records[1].get("route") != "updateLibrary"
                or records[1].get("state") != "received"):
            raise SongUploadError("元数据提交结果尚未确认，不能自动恢复")
        raw = base64.b64decode(records[1]["response"])
        metadata_result = plistlib.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b\x08") else raw)
        if metadata_result.get("status") != 0:
            raise SongUploadError("元数据尚未被接受，不能恢复工作查询")
        self._media(source, self.private / f"media-{digest}")
        self.common = {k: v for k, v in self.context["common"].items() if k not in ("num-tracks", "update-id")}
        self.common.update(incremental=True, **{"cloud-incremental-update": True, "auto-update": False})
        raw = base64.b64decode(records[0]["response"])
        initial = plistlib.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b\x08") else raw)
        self.signer = WindowsSapSigner()
        return self._finish(initial, self.state["track_id"])

    def resume_work(self, source):
        """恢复已收到明确工作响应的单曲，不重复提交元数据。"""
        source = Path(source).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.job = self.private / f"upload-{digest}.dpapi"
        self.state = load_session(self.job)
        self._check_job_context(self.state)
        if self.state.get("completed") or not self.state.get("cloud_id") or not self.state.get("status"):
            raise SongUploadError("此记录不属于工作任务中断会话")
        record = self.state["requests"][-1]
        if record.get("state") != "received" or record.get("route") not in ("downloadRequests", "uploadResponses"):
            raise SongUploadError("最后工作请求结果尚未确认，不能自动恢复")
        raw = base64.b64decode(record["response"])
        reply = plistlib.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b\x08") else raw)
        if reply.get("status") != 0:
            raise SongUploadError("最后工作响应未成功，停止恢复")
        self._media(source, self.private / f"media-{digest}")
        self.common = {k: v for k, v in self.context["common"].items() if k not in ("num-tracks", "update-id")}
        self.common.update(incremental=True, **{"cloud-incremental-update": True, "auto-update": False})
        self.signer = WindowsSapSigner()
        return self._finish(None, self.state["track_id"], resume_reply=reply)

    def _await_status(self, initial):
        """遵守服务端处理元数据时返回的等待时间。"""
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            status = self._post(self.account["upload_configuration"]["cloud-library-update-check"],
                                {**self.common, "update-id": initial["update-id"]})
            if "additional-fields-url" in status and "download-requests-url" in status:
                return status
            delay = status.get("retry-in-ms", 0)
            if type(delay) is not int or delay <= 0:
                raise SongUploadError("状态响应没有工作路由或有效等待时间")
            delay = min(delay, 60000)
            self.progress("metadata-processing", delay // 1000)
            time.sleep(delay / 1000)
        raise SongUploadError("元数据仍在服务端处理中；可从等待会话恢复")

    def _refresh_work_status(self):
        """仅刷新原更新的工作路由，拒绝切换到其他会话。"""
        previous = plistlib.loads(base64.b64decode(self.state["status"]))
        initial = plistlib.loads(base64.b64decode(self.state["initial"]))
        status = self._await_status(initial)
        if not previous.get("session-id") or status.get("session-id") != previous["session-id"]:
            raise UploadSessionChanged("工作路由刷新返回了其他会话；保留原记录供核对")
        self.state["status"] = base64.b64encode(plistlib.dumps(status)).decode("ascii")
        save_session(self.job, self.state)
        return status

    def _finish(self, initial, track_id, resume_reply=None):
        self.progress("check-session")
        if resume_reply is None:
            status = self._await_status(initial)
            mappings = self._post(status["additional-fields-url"], self.common, "getLibraryUpdateResponse", False)
            owned = next(t["cloud-id"] for t in mappings["tracks"] if t["persistent-id"] == track_id)
            self.state["cloud_id"] = owned
            self.state["initial"] = base64.b64encode(plistlib.dumps(initial)).decode("ascii")
            self.state["status"] = base64.b64encode(plistlib.dumps(status)).decode("ascii")
        else:
            status = plistlib.loads(base64.b64decode(self.state["status"]))
            owned = self.state["cloud_id"]
        sequence = self.state.get("sequence_id", 0)
        match_state = self.state.get("match_state", 12)
        pending = []
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            payload = {**self.common, "session-id": status["session-id"], "match-state": match_state, "work-in-progress": False}
            if resume_reply is not None:
                reply, resume_reply = resume_reply, None
            elif pending:
                payload["payload"] = pending
                reply = self._post(status["upload-responses-url"], payload, "uploadResponses")
                pending = []
            else:
                if sequence:
                    payload["sequence-id"] = sequence
                reply = self._post(status["download-requests-url"], payload, "downloadRequests")
                if match_state == 12:
                    match_state = 13
            sequence = reply.get("sequence-id", sequence)
            for ticket in reply.get("payload", []):
                if ticket["cloud-id"] != owned:
                    raise SongUploadError("服务端返回了其他歌曲任务，停止处理")
                names = {action["action"] for action in ticket["actions"]}
                if names & {"prepare-track", "upload-track"}:
                    match_state = 5
                elif names & {"hash-track", "get-fingerprint", "prepare-fingerprint", "upload-fingerprint"}:
                    match_state = 13
                actions = [self._action(action) for action in ticket["actions"]]
                actions = [action for action in actions if action is not None]
                if actions:
                    pending.append({"cloud-id": owned, "actions": actions})
            if reply.get("all-work-completed") is True:
                if not self.state["complete_received"]:
                    raise SongUploadError("会话结束但未收到单曲完成票据")
                self.state["completed"] = True
                save_session(self.job, self.state)
                result = {"completed": True, "audio_uploaded": self.state["audio_uploaded"], "client_rpc_used": False}
                result.update(self.upload_media_extras(self.source))
                return result
            self.state["match_state"] = match_state
            self.state["sequence_id"] = sequence
            save_session(self.job, self.state)
            if not pending:
                delay = reply.get("retry-in-ms", reply.get("back-off-delay-in-ms", 1000))
                if type(delay) is not int or not 0 <= delay <= 600000:
                    raise SongUploadError("工作响应等待时间超出支持范围")
                delay = max(delay, 1000)
                self.progress("waiting", delay // 1000)
                time.sleep(delay / 1000)
                self.progress("check-session")
                if delay >= 180000:
                    status = self._refresh_work_status()
        raise SongUploadError("上传会话尚未在等待期限内完成；保留记录供恢复")
