"""上传执行器专用接口与用户侧脱敏上传状态。"""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.apple_music_upload import apple_music_upload_service as service, UploadConflict
from app.services.configuration_backup import current_general, apply_general
from app.services.config_manager import config_manager

router = APIRouter()


def worker_identity(authorization: str = Header(default=""), x_worker_id: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少工作进程凭据")
    try:
        scope = service.authenticate(x_worker_id, authorization[7:])
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from None
    return x_worker_id, scope


class Readiness(BaseModel):
    authorization_saved: bool = False
    client_exited: bool = False
    compatible: bool = False
    context_matches: bool = False
    server_verified_at: float | None = None
    scheduler_error: Literal["process_start_failed"] | None = None


class Claim(BaseModel):
    account_scope: str
    protocol_version: Literal[1, 2]
    readiness: Readiness


class Evidence(BaseModel):
    complete_received: bool = False
    all_work_completed: bool = False
    extras_completed: bool = False


class Event(BaseModel):
    lease_token: str = Field(min_length=20, max_length=128)
    sequence: int = Field(ge=1)
    state: str = Field(max_length=48)
    stage: Literal["download", "validation", "signature", "metadata", "audio", "extras", "processing", "complete",
                   "media", "hash", "partial", "full-lowres", "decode", "fingerprint-upload", "prepare-track", "waiting", "extras-waiting", "session-wait"] | None = None
    action: str = "upload"
    error_code: str | None = Field(default=None, max_length=48)
    evidence: Evidence = Field(default_factory=Evidence)
    bytes_sent: int | None = Field(default=None, ge=0)
    bytes_total: int | None = Field(default=None, ge=0)
    signature_progress: int | None = Field(default=None, ge=0, le=100, strict=True)
    signature_elapsed_seconds: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False)
    stage_progress: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    stage_token: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    wait_seconds: float | None = Field(default=None, ge=0, le=600, allow_inf_nan=False)


class CreateUpload(BaseModel):
    conversion_task_id: str


class RetryUpload(BaseModel):
    action: str


class UploadConcurrency(BaseModel):
    concurrency: int = Field(ge=1, le=5, strict=True)


class Lease(BaseModel):
    lease_token: str = Field(min_length=20, max_length=128)


@router.put("/workers/concurrency")
def save_concurrency(request: UploadConcurrency):
    value = current_general().model_copy(update={"apple_music_upload_concurrency": request.concurrency})
    if not config_manager.save("settings.json", value.model_dump()):
        raise HTTPException(500, "上传并发保存失败")
    apply_general(value)
    return service.worker_status()


@router.post("/workers/control")
def controls(request: Readiness, identity=Depends(worker_identity)):
    return service.controls(identity[0], request.model_dump())


@router.post("/uploads/{job_id}/settled")
def settled(job_id: str, request: Lease, identity=Depends(worker_identity)):
    try:
        return service.settled(job_id, identity[0], request.lease_token)
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/uploads/{job_id}/stop")
def stop_upload(job_id: str):
    try:
        return service.stop(job_id)
    except KeyError:
        raise HTTPException(404, "上传任务不存在") from None
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.delete("/uploads/{job_id}")
def delete_upload(job_id: str, conversion_task_id: str | None = None):
    try:
        return service.delete(job_id, conversion_task_id)
    except KeyError:
        raise HTTPException(404, "上传任务不存在") from None
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/workers/status")
def worker_status():
    return service.worker_status()


@router.post("/workers/claim")
def claim(request: Claim, identity=Depends(worker_identity)):
    worker_id, scope = identity
    if request.account_scope != scope:
        raise HTTPException(403, "账号绑定不一致")
    return {"job": service.claim(worker_id, scope, request.readiness.model_dump(), managed=request.protocol_version == 2),
            "concurrency": current_general().apple_music_upload_concurrency, "retry_after": 5}


@router.post("/uploads")
def create_upload(request: CreateUpload):
    from app.api.routes.tasks import tasks_cache, register_direct_upload, save_tasks

    task = tasks_cache.get(request.conversion_task_id)
    if not task or task.status != "success" or task.apple_music_delivery_mode == "client_import" or task.apple_music_import_file:
        raise HTTPException(400, "只能提交已完成且未交给官方客户端导入的成品")
    if task.apple_music_delivery_mode != "direct_upload":
        worker = service.worker_status()
        if not worker.get("bound"):
            raise HTTPException(409, "请先导入服务端授权并等待上传执行器就绪")
        task.apple_music_delivery_mode = "direct_upload"
        task.apple_music_account_scope = worker["account_scope"]
        task.apple_music_status = "delivery_pending"
        save_tasks()
    try:
        return register_direct_upload(task)
    except (UploadConflict, OSError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/uploads")
def list_uploads():
    from app.api.routes.tasks import tasks_cache
    from app.services.profile_manager import profile_manager

    uploads = service.list_uploads()
    for upload in uploads:
        for source in upload["sources"]:
            task = tasks_cache.get(source["conversion_task_id"])
            profile = profile_manager.get_profile(task.profile_id) if task else None
            source["profile_name"] = profile.name if profile else "原转换方案不可用"
    return uploads


@router.get("/uploads/{job_id}")
def get_upload(job_id: str):
    try:
        return service.get(job_id)
    except KeyError:
        raise HTTPException(404, "上传任务不存在") from None


@router.post("/uploads/{job_id}/retry")
def retry_upload(job_id: str, request: RetryUpload):
    try:
        return service.retry(job_id, request.action)
    except KeyError:
        raise HTTPException(404, "上传任务不存在") from None
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/uploads/{job_id}/content")
def content(job_id: str, x_upload_lease: str = Header(default=""), identity=Depends(worker_identity)):
    try:
        path = service.content(job_id, identity[0], x_upload_lease)
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return FileResponse(path, media_type="audio/mp4", filename=f"{job_id}.m4a")


@router.post("/uploads/{job_id}/cancel")
def cancel_upload(job_id: str):
    try:
        return service.cancel(job_id)
    except KeyError:
        raise HTTPException(404, "上传任务不存在") from None
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/uploads/{job_id}/events")
def event(job_id: str, request: Event, identity=Depends(worker_identity)):
    try:
        return service.event(job_id, identity[0], request.model_dump())
    except UploadConflict as exc:
        raise HTTPException(409, str(exc)) from None
