"""独立上传队列的幂等、租约、恢复与文件访问回归。"""

from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from fastapi import FastAPI
import pytest

from app.api.routes import apple_music_uploads as api
from app.models import Profile
from app.services.apple_music_upload import AppleMusicUploadService, UploadConflict


READY = dict(authorization_saved=True, client_exited=True, compatible=True, context_matches=True)


def asgi_request(app, method, path, payload=None, headers=None):
    """直接运行 ASGI 应用，避免为接口回归新增 HTTP 客户端依赖。"""
    async def run():
        messages = []

        async def receive():
            return {"type": "http.request", "body": json.dumps(payload).encode() if payload else b"", "more_body": False}

        async def send(message):
            messages.append(message)

        request_headers = {"Content-Type": "application/json", **(headers or {})}
        await app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "method": method,
                   "path": path, "raw_path": path.encode(), "query_string": b"", "scheme": "http", "root_path": "",
                   "http_version": "1.1", "server": ("test", 80), "client": ("test", 1),
                   "headers": [(key.lower().encode(), value.encode()) for key, value in request_headers.items()]}, receive, send)
        body = b"".join(item.get("body", b"") for item in messages)
        return SimpleNamespace(status_code=messages[0]["status"], content=body, json=lambda: json.loads(body))

    return asyncio.run(run())


@pytest.fixture
def queue(tmp_path):
    service = AppleMusicUploadService(tmp_path / "queue.db")
    binding = service.bind_worker()
    source = tmp_path / "中文 空格 & 歌曲.m4a"
    source.write_bytes(b"final-tagged-m4a")
    return service, binding, source


def enqueue(queue, task_id="conversion-1"):
    service, binding, source = queue
    return service.enqueue(task_id, "/source/song.flac", source, binding["account_scope"])


def claim(queue):
    service, binding, _ = queue
    return service.claim(binding["worker_id"], binding["account_scope"], READY)


def event(job, sequence=1, **changes):
    return {"lease_token": job["lease_token"], "sequence": sequence, "state": "uploading", "stage": "audio", **changes}


def test_重复提交和并发提交只生成一个上传任务(queue):
    service, _, _ = queue
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = list(executor.map(lambda index: enqueue(queue, f"task-{index}"), range(3)))
    assert len({job["id"] for job in jobs}) == 1
    assert enqueue(queue, "task-0")["id"] == jobs[0]["id"]
    with service.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM apple_uploads").fetchone()[0] == 1


def test_队列重启后任务和关联保留(queue):
    service, _, _ = queue
    job = enqueue(queue)
    restarted = AppleMusicUploadService(service.database_path)
    assert restarted.for_task("conversion-1")["id"] == job["id"]
    assert restarted.for_source("/source/song.flac")["id"] == job["id"]


def test_工作进程鉴权和账号绑定拒绝越权(queue):
    service, binding, source = queue
    assert service.authenticate(binding["worker_id"], binding["token"]) == binding["account_scope"]
    with pytest.raises(PermissionError):
        service.authenticate(binding["worker_id"], "wrong-token")
    with pytest.raises(UploadConflict):
        service.enqueue("bad", "source", source, "other-account")
    with pytest.raises(UploadConflict):
        service.bind_worker()
    assert "token" not in str(service.worker_status())


@pytest.mark.parametrize("missing", READY)
def test_本机任一条件不满足时不领取(queue, missing):
    service, binding, _ = queue
    job = enqueue(queue)
    assert service.claim(binding["worker_id"], binding["account_scope"], {**READY, missing: False}) is None
    assert service.get(job["id"])["state"] != "queued"


def test_同一时间仅领取一首且有效租约不被替换(queue):
    service, binding, source = queue
    first = enqueue(queue)
    source.write_bytes(b"different-final-song")
    enqueue(queue, "task-2")
    leased = claim(queue)
    assert leased["job_id"] == first["id"]
    assert claim(queue) is None
    assert "lease_token" not in service.get(first["id"])


def test_重复事件幂等且旧租约和乱序事件被拒绝(queue):
    service, binding, _ = queue
    enqueue(queue)
    job = claim(queue)
    accepted = service.event(job["job_id"], binding["worker_id"], event(job))
    assert service.event(job["job_id"], binding["worker_id"], event(job)) == accepted
    for payload in (event(job, 3), event(job, 2, lease_token="invalid-lease")):
        with pytest.raises(UploadConflict):
            service.event(job["job_id"], binding["worker_id"], payload)


def test_签名进度持久化并兼容旧执行器(queue):
    service, binding, _ = queue
    enqueue(queue)
    job = claim(queue)
    service.event(job['job_id'], binding['worker_id'], event(job, stage='signature', signature_progress=42, signature_elapsed_seconds=90.5))
    restarted = AppleMusicUploadService(service.database_path)
    result = restarted.get(job['job_id'])
    assert result['signature_progress'] == 42
    assert result['signature_elapsed_seconds'] == 90.5
    service.event(job['job_id'], binding['worker_id'], event(job, sequence=2))
    assert service.get(job['job_id'])['signature_progress'] is None
    service.event(job['job_id'], binding['worker_id'], event(job, sequence=3, state='failed', action='resume_work', signature_progress=42, signature_elapsed_seconds=90.5))
    assert service.retry(job['job_id'], 'resume_work')['signature_progress'] is None


@pytest.mark.parametrize('changes', [{'signature_progress': -1}, {'signature_progress': 101}, {'signature_progress': True}, {'signature_elapsed_seconds': -1}, {'signature_elapsed_seconds': float('inf')}])
def test_签名进度拒绝非法数值(changes):
    with pytest.raises(ValueError):
        api.Event(lease_token='x' * 24, sequence=1, state='uploading', stage='signature', **changes)


def test_旧数据库升级保留任务并支持并发初始化(queue):
    service, _, _ = queue
    job = enqueue(queue)
    with service.connect() as connection:
        connection.execute('ALTER TABLE apple_uploads DROP COLUMN signature_progress')
        connection.execute('ALTER TABLE apple_uploads DROP COLUMN signature_elapsed_seconds')
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: service.get(job['id']), range(3)))
    assert all(item['id'] == job['id'] and item['signature_progress'] is None for item in results)


def test_过期任务只归还原工作进程且拒绝旧租约(queue):
    service, binding, _ = queue
    enqueue(queue)
    old = claim(queue)
    with service.connect() as connection:
        connection.execute("UPDATE apple_uploads SET lease_until = ?", (time.time() - 1,))
    assert service.claim("another-worker", binding["account_scope"], READY) is None
    restored = claim(queue)
    assert restored["job_id"] == old["job_id"]
    assert restored["lease_token"] != old["lease_token"]
    with pytest.raises(UploadConflict):
        service.event(old["job_id"], binding["worker_id"], event(old))


def test_下载仅开放租约登记成品且拒绝后续修改(queue):
    service, binding, source = queue
    enqueue(queue)
    job = claim(queue)
    assert service.content(job["job_id"], binding["worker_id"], job["lease_token"]) == source.resolve()
    with pytest.raises(UploadConflict):
        service.content(job["job_id"], "other-worker", job["lease_token"])
    source.write_bytes(b"modified")
    with pytest.raises(UploadConflict):
        service.content(job["job_id"], binding["worker_id"], job["lease_token"])


def test_没有全部完成票据时不能报告云端完成(queue):
    service, binding, _ = queue
    enqueue(queue)
    job = claim(queue)
    with pytest.raises(UploadConflict):
        service.event(job["job_id"], binding["worker_id"], event(job, state="cloud_completed", evidence={"complete_received": True}))
    assert service.get(job["job_id"])["state"] == "staging"


def test_云端完成不阻塞下一首也不被过期重领(queue):
    service, binding, source = queue
    enqueue(queue)
    job = claim(queue)
    done = event(job, state="cloud_completed", evidence={key: True for key in ("complete_received", "all_work_completed", "extras_completed")})
    service.event(job["job_id"], binding["worker_id"], done)
    assert service.event(job["job_id"], binding["worker_id"], done)["accepted"]
    with pytest.raises(UploadConflict):
        service.event(job["job_id"], binding["worker_id"], event(job, 2))
    source.write_bytes(b"song-2")
    next_job = enqueue(queue, "task-2")
    with service.connect() as connection:
        connection.execute("UPDATE apple_uploads SET lease_until = 0 WHERE id = ?", (job["job_id"],))
    assert claim(queue)["job_id"] == next_job["id"]


def test_结果不明不允许自动重领或点击重试(queue):
    service, binding, _ = queue
    enqueue(queue)
    job = claim(queue)
    service.event(job["job_id"], binding["worker_id"], event(job, state="requires_review", error_code="request_uncertain"))
    assert service.get(job["job_id"])["allowed_actions"] == []
    with pytest.raises(UploadConflict):
        service.retry(job["job_id"], "upload")
    assert claim(queue) is None


def test_资产失败仅提供补传动作并递增恢复轮次(queue):
    service, binding, _ = queue
    enqueue(queue)
    job = claim(queue)
    service.event(job["job_id"], binding["worker_id"], event(job, state="media_completed_extras_pending", action="upload_media_extras"))
    with pytest.raises(UploadConflict):
        service.retry(job["job_id"], "upload")
    service.retry(job["job_id"], "upload_media_extras")
    restored = claim(queue)
    assert restored["attempt"] == 1
    assert restored["action"] == "upload_media_extras"


def test_取消只允许尚未领取的任务(queue):
    service, _, _ = queue
    job = enqueue(queue)
    service.cancel(job["id"])
    assert claim(queue) is None
    with pytest.raises(UploadConflict):
        service.retry(job["id"], "upload")


def test_接口鉴权成品下载和事件校验(queue, monkeypatch):
    service, binding, source = queue
    monkeypatch.setattr(api, "service", service)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/apple-music")
    enqueue(queue)
    headers = {"Authorization": "Bearer " + binding["token"], "X-Worker-Id": binding["worker_id"]}
    payload = {"protocol_version": 1, "account_scope": binding["account_scope"], "readiness": READY}
    assert asgi_request(app, "POST", "/api/apple-music/workers/claim", payload).status_code == 401
    assert asgi_request(app, "POST", "/api/apple-music/workers/claim", {**payload, "account_scope": "wrong"}, headers).status_code == 403
    job = asgi_request(app, "POST", "/api/apple-music/workers/claim", payload, headers).json()["job"]
    assert asgi_request(app, "GET", job["content_url"], headers=headers).status_code == 409
    response = asgi_request(app, "GET", job["content_url"], headers={**headers, "X-Upload-Lease": job["lease_token"]})
    assert response.content == source.read_bytes()
    assert hashlib.sha256(response.content).hexdigest() == job["sha256"]
    assert asgi_request(app, "POST", f"/api/apple-music/uploads/{job['job_id']}/events", event(job, sequence=0), headers).status_code == 422


def test_旧配置兼容且直接上传限制输出编码():
    assert Profile(id="old", name="旧配置", output_format="m4a", apple_music_handoff_enabled=True).apple_music_delivery_mode == "client_import"
    direct = Profile(id="new", name="新配置", output_format="m4a", codec="aac", apple_music_delivery_mode="direct_upload", apple_music_handoff_enabled=True)
    assert direct.apple_music_handoff_enabled is False
    with pytest.raises(ValueError):
        Profile(id="bad", name="错误编码", output_format="flac", apple_music_delivery_mode="direct_upload")


def test_队列暂时失败不改变转换成功并可恢复登记(queue, monkeypatch):
    import sqlite3
    from app.api.routes import tasks
    from app.services import apple_music_upload as upload_module

    service, binding, source = queue
    monkeypatch.setattr(upload_module, "apple_music_upload_service", service)
    task = tasks.TaskResponse(id="done", source_file="source", output_file=str(source), profile_id="profile",
                              status="success", apple_music_delivery_mode="direct_upload", apple_music_status="delivery_pending",
                              apple_music_account_scope=binding["account_scope"])
    monkeypatch.setattr(tasks, "tasks_cache", {task.id: task})
    with monkeypatch.context() as temporary:
        temporary.setattr(service, "enqueue", lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("busy")))
        tasks.refresh_direct_uploads()
    assert task.status == "success"
    assert task.apple_music_error
    tasks.refresh_direct_uploads()
    assert task.apple_music_upload["id"] == service.for_task(task.id)["id"]
    assert task.apple_music_error is None


@pytest.mark.parametrize("metadata_ok", [True, False])
def test_直接上传在标签成功并重新校验后才登记待交付(tmp_path, monkeypatch, metadata_ok):
    from app.models import Task
    from app.services import conversion_engine as engine_module

    source, output = tmp_path / "source.flac", tmp_path / "final.m4a"
    source.write_bytes(b"source")
    profile = Profile(id="p", name="直接上传", output_format="m4a", codec="aac", apple_music_delivery_mode="direct_upload")
    task = Task(id="t", source_file=str(source), output_file=str(output), profile_id="p", status="waiting")
    probes = []

    def probe(path):
        probes.append(Path(path).read_bytes())
        return {"codec": "aac"}

    def convert(**kwargs):
        output.write_bytes(b"converted")
        return True

    def metadata(path, value):
        output.write_bytes(b"final-tags")
        return metadata_ok

    monkeypatch.setattr(engine_module.ffprobe_service, "get_audio_info", probe)
    monkeypatch.setattr(engine_module.ffmpeg_service, "convert", convert)
    monkeypatch.setattr(engine_module.metadata_service, "read_metadata", lambda path: {"title": "测试"})
    monkeypatch.setattr(engine_module.metadata_service, "write_metadata", metadata)
    engine = engine_module.ConversionEngine()
    try:
        result = engine._run_conversion_sync(task, profile, None)
    finally:
        engine.executor.shutdown()
    assert result is metadata_ok
    if metadata_ok:
        assert probes[-1] == b"final-tags"
        assert task.apple_music_status == "delivery_pending"
    else:
        assert task.apple_music_status is None
        assert task.status == "failed"


def test_绑定文件写入失败不遗留不可恢复的账号绑定(queue):
    service, _, _ = queue
    empty = AppleMusicUploadService(service.database_path.with_name("new.db"))

    def fail(binding):
        raise OSError("disk-full")

    with pytest.raises(OSError):
        empty.bind_worker(fail)
    assert empty.worker_status()["bound"] is False


def test_补齐任务恢复上传不重新下载或转码(queue, monkeypatch):
    from app.services.acquisition_service import AcquisitionService
    from app.services import apple_music_upload as upload_module

    service, binding, source = queue
    monkeypatch.setattr(upload_module, "apple_music_upload_service", service)
    acquisition = AcquisitionService(service.database_path)
    started = []
    monkeypatch.setattr(acquisition, "start", lambda task_id: started.append(task_id))
    job = acquisition.create_job(None, "file-id", str(source), False, True)
    acquisition._update(job["id"], apple_watch_path="/source/song.flac", apple_delivery_mode="direct_upload", apple_status="submitted", status="completed")
    upload = enqueue(queue)
    lease = claim(queue)
    service.event(upload["id"], binding["worker_id"], event(lease, state="failed", action="resume_work", error_code="upload_failed"))
    started.clear()
    result = acquisition.retry(job["id"])
    assert started == []
    assert result["apple_upload"]["id"] == upload["id"]
    assert result["apple_status"] == "queued"


def test_云端完成不自动变成资料库快照确认(queue, monkeypatch):
    from app.services.acquisition_service import AcquisitionService
    from app.services import apple_music_upload as upload_module

    service, binding, source = queue
    monkeypatch.setattr(upload_module, "apple_music_upload_service", service)
    acquisition = AcquisitionService(service.database_path)
    monkeypatch.setattr(acquisition, "start", lambda task_id: None)
    job = acquisition.create_job(None, "file-id", str(source), False, True)
    acquisition._update(job["id"], apple_watch_path="/source/song.flac", apple_status="submitted", status="completed")
    upload = enqueue(queue)
    lease = claim(queue)
    service.event(upload["id"], binding["worker_id"], event(lease, state="cloud_completed", evidence={key: True for key in ("complete_received", "all_work_completed", "extras_completed")}))
    assert acquisition.get_job(job["id"])["apple_status"] == "cloud_completed"


def test_独立上传增量来源保持待快照确认(queue):
    from app.services.dual_library_service import DualLibraryService

    service, _, _ = queue
    library = DualLibraryService(service.database_path)
    entry = library.upsert_incremental_track({"title": "测试曲目", "artist": "测试歌手", "album": "测试专辑"}, source="direct_upload")
    assert entry["source"] == "direct_upload"
    assert entry["verification_status"] == "pending"


def test_阶段时间线保留重复等待且幂等重报不重复记账(queue, monkeypatch):
    service, binding, _ = queue
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1000)
    upload = enqueue(queue)
    job = claim(queue)
    first = event(job, stage="waiting", stage_token=1, wait_seconds=180)
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1010)
    service.event(upload["id"], binding["worker_id"], first)
    service.event(upload["id"], binding["worker_id"], first)
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1020)
    service.event(upload["id"], binding["worker_id"], event(job, 2, stage="waiting", stage_token=1, wait_seconds=180))
    timeline = service.get(upload["id"])["timeline"]
    assert len(timeline) == 2
    assert timeline[-1]["wait_until"] == 1190
    service.event(upload["id"], binding["worker_id"], event(job, 3, stage="waiting", stage_token=2, wait_seconds=180))
    timeline = service.get(upload["id"])["timeline"]
    assert len(timeline) == 3
    assert timeline[-2]["elapsed_seconds"] == 10
    assert timeline[-1]["wait_until"] == 1200


def test_完成后总耗时冻结且重启保留明细(queue, monkeypatch):
    service, binding, _ = queue
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1000)
    upload = enqueue(queue)
    job = claim(queue)
    service.event(upload["id"], binding["worker_id"], event(job, stage="full-lowres", stage_progress=40))
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1030)
    service.event(upload["id"], binding["worker_id"], event(job, 2, state="cloud_completed", stage="complete", evidence={key: True for key in ("complete_received", "all_work_completed", "extras_completed")}))
    monkeypatch.setattr("app.services.apple_music_upload.time.time", lambda: 1100)
    value = AppleMusicUploadService(service.database_path).get(upload["id"])
    assert value["finished_at"] == 1030
    assert value["elapsed_seconds"] == 30
    assert sum(item["elapsed_seconds"] for item in value["timeline"]) == 30
    assert value["timeline"][-1]["progress"] == 40


def test_恢复保留前轮耗时且取消关闭排队阶段(queue):
    service, binding, _ = queue
    upload = enqueue(queue)
    job = claim(queue)
    service.event(upload["id"], binding["worker_id"], event(job, state="failed", action="resume_work", error_code="upload_failed"))
    service.retry(upload["id"], "resume_work")
    service.cancel(upload["id"])
    value = service.get(upload["id"])
    assert len(value["timeline"]) == 2
    assert all(item["ended_at"] is not None for item in value["timeline"])


def test_阶段进度拒绝非有限数及越界输入():
    from app.api.routes.apple_music_uploads import Event
    from pydantic import ValidationError
    for changes in ({"stage_progress": 101}, {"stage_progress": float("nan")}, {"stage_token": float("inf")}, {"wait_seconds": 601}):
        with pytest.raises(ValidationError):
            Event(lease_token="x" * 32, sequence=1, state="uploading", **changes)
