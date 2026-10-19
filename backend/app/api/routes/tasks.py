import logging
import uuid
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_serializer
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# 任务存储（内存缓存）
tasks_cache: dict = {}

# 任务持久化文件路径
TASKS_FILE = Path(settings.CONFIG_DIR) / "tasks.json"


class TaskStatus(str, Enum):
    WAITING = "waiting"
    CONVERTING = "converting"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TaskCreate(BaseModel):
    source_file: str
    output_file: str
    profile_id: str


class TaskBatchAction(BaseModel):
    task_ids: List[str]


class TaskResponse(BaseModel):
    id: str
    source_file: str
    output_file: str
    profile_id: str
    status: TaskStatus
    progress: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    apple_music_status: Optional[str] = None
    apple_music_import_file: Optional[str] = None
    apple_music_error: Optional[str] = None
    apple_music_delivery_mode: Optional[str] = None
    apple_music_account_scope: Optional[str] = None
    apple_music_upload: Optional[dict] = None

    @field_serializer('start_time', 'end_time', when_used='json')
    def serialize_task_time(self, value):
        # 旧记录使用服务端本地时间，响应统一带 UTC 时区，避免浏览器按自身时区猜测。
        return value.astimezone(timezone.utc).isoformat() if value else None


def register_direct_upload(task):
    """幂等登记已完成成品；入队失败不重新转码。"""
    from app.services.apple_music_upload import apple_music_upload_service

    return apple_music_upload_service.enqueue(task.id, task.source_file, task.output_file, task.apple_music_account_scope)


def refresh_direct_uploads():
    from app.services.apple_music_upload import apple_music_upload_service

    for task in tasks_cache.values():
        if task.apple_music_delivery_mode != "direct_upload" or task.status != TaskStatus.SUCCESS:
            continue
        try:
            task.apple_music_upload = apple_music_upload_service.for_task(task.id)
            if task.apple_music_upload is None and task.apple_music_status == "delivery_pending":
                task.apple_music_upload = register_direct_upload(task)
                task.apple_music_error = None
        except (ValueError, OSError, sqlite3.Error):
            task.apple_music_error = "上传队列暂不可用或成品校验失败，转换成品已保留"


def refresh_apple_music_statuses():
    """刷新已交接任务的本地接收状态，不检查 Apple 云端上传状态。"""
    from app.services.apple_music_handoff import apple_music_handoff_service

    changed = False
    for task in tasks_cache.values():
        if task.apple_music_delivery_mode == "direct_upload":
            continue
        if task.apple_music_status != "waiting" or not task.apple_music_import_file:
            continue
        try:
            received = apple_music_handoff_service.is_received(task.apple_music_import_file)
        except OSError as exc:
            task.apple_music_status = "failed"
            task.apple_music_error = str(exc)
            logger.warning(f"Apple Music 交接状态检查失败：{task.id}: {exc}")
            changed = True
            continue
        if received:
            task.apple_music_status = "received"
            task.apple_music_error = None
            changed = True
    if changed:
        save_tasks()


def load_tasks():
    """从文件加载任务"""
    global tasks_cache
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                for task_id, task_dict in data.items():
                    # 转换时间字符串为 datetime 对象
                    if task_dict.get('start_time'):
                        task_dict['start_time'] = datetime.fromisoformat(task_dict['start_time'])
                    if task_dict.get('end_time'):
                        task_dict['end_time'] = datetime.fromisoformat(task_dict['end_time'])
                    tasks_cache[task_id] = TaskResponse(**task_dict)
            logger.info(f"Loaded {len(tasks_cache)} tasks from file")
    except Exception as e:
        logger.error(f"Error loading tasks: {e}")


def save_tasks():
    """保存任务到文件"""
    try:
        # 确保目录存在
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 转换为可序列化的格式
        data = {}
        for task_id, task in tasks_cache.items():
            task_dict = task.dict()
            # 转换 datetime 为字符串
            if task_dict.get('start_time'):
                task_dict['start_time'] = task_dict['start_time'].astimezone(timezone.utc).isoformat()
            if task_dict.get('end_time'):
                task_dict['end_time'] = task_dict['end_time'].astimezone(timezone.utc).isoformat()
            data[task_id] = task_dict

        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(tasks_cache)} tasks to file")
    except Exception as e:
        logger.error(f"Error saving tasks: {e}")


# 进度回调函数 - 更新 tasks_cache 中的任务状态
def update_task_progress(task_id: str, progress: float, status: str = None, apple_music_status: str = None,
                         apple_music_import_file: str = None, apple_music_error: str = None):
    """更新任务进度"""
    if task_id in tasks_cache:
        task = tasks_cache[task_id]
        task.progress = progress
        if status:
            task.status = TaskStatus(status)
        if status in ['success', 'failed', 'cancelled']:
            task.end_time = datetime.now()
        if apple_music_status is not None:
            task.apple_music_status = apple_music_status
            task.apple_music_import_file = apple_music_import_file
            task.apple_music_error = apple_music_error
        logger.info(f"Task {task_id} progress: {progress}%, status: {status}")
        # 保存任务到文件
        save_tasks()
        if status == 'success' and task.apple_music_delivery_mode == 'direct_upload':
            refresh_direct_uploads()


@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    status: Optional[TaskStatus] = Query(None, description="状态筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制")
):
    """获取所有任务"""
    refresh_apple_music_statuses()
    refresh_direct_uploads()
    tasks = list(tasks_cache.values())

    # 状态筛选
    if status:
        tasks = [t for t in tasks if t.status == status]

    # 最新记录始终优先返回，无时间记录排在最后
    tasks.sort(
        key=lambda task: task.start_time.timestamp() if task.start_time else float("-inf"),
        reverse=True,
    )

    # 限制返回数量
    return tasks[:limit]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取单个任务详情"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    refresh_direct_uploads()
    return tasks_cache[task_id]


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任意状态的任务记录。"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    delete_upload_links([task_id])
    del tasks_cache[task_id]
    save_tasks()
    logger.info(f"Deleted task record {task_id}")

    return {"status": "success", "deleted": 1}


async def enqueue_conversion_task(
    task_create: TaskCreate,
    skip_existing: bool = False,
) -> Optional[TaskResponse]:
    """创建并提交转换任务，供 API 与目录监控共同使用。"""
    output_path = Path(task_create.output_file)
    if skip_existing:
        if output_path.exists():
            logger.info(f"Skipping existing output: {output_path}")
            return None
        for existing in tasks_cache.values():
            same_task = (
                existing.source_file == task_create.source_file
                and existing.output_file == task_create.output_file
                and existing.profile_id == task_create.profile_id
            )
            if same_task and existing.status in {
                TaskStatus.WAITING,
                TaskStatus.CONVERTING,
            }:
                logger.info(f"Skipping duplicate active task: {existing.id}")
                return None

    task_id = str(uuid.uuid4())

    task = TaskResponse(
        id=task_id,
        source_file=task_create.source_file,
        output_file=task_create.output_file,
        profile_id=task_create.profile_id,
        status=TaskStatus.WAITING,
        start_time=datetime.now(),
    )

    tasks_cache[task_id] = task
    logger.info(f"Created task {task_id}: {task_create.source_file}")

    # 保存任务到文件
    save_tasks()

    # 自动触发转换引擎执行任务
    try:
        from app.services.conversion_engine import conversion_engine
        from app.services.profile_manager import profile_manager
        from app.models import Task, Profile, TaskStatus as ModelTaskStatus

        # 获取 Profile
        profile = profile_manager.get_profile(task_create.profile_id)
        if profile:
            task.apple_music_delivery_mode = profile.apple_music_delivery_mode
            if task.apple_music_delivery_mode == "direct_upload":
                from app.services.apple_music_upload import apple_music_upload_service
                worker = apple_music_upload_service.worker_status()
                if not worker.get("bound"):
                    raise ValueError("请先导入服务端授权并等待上传执行器就绪")
                task.apple_music_account_scope = worker["account_scope"]
            # 创建模型任务
            model_task = Task(
                id=task_id,
                source_file=task_create.source_file,
                output_file=task_create.output_file,
                profile_id=task_create.profile_id,
                status=ModelTaskStatus.WAITING,
                start_time=datetime.now(),
                apple_music_delivery_mode=task.apple_music_delivery_mode,
                apple_music_account_scope=task.apple_music_account_scope,
            )

            # 提交到转换引擎，传入进度回调
            submitted = await conversion_engine.submit_task(
                model_task,
                profile,
                progress_callback=lambda t: update_task_progress(
                    t.id,
                    t.progress or 0,
                    t.status.value if t.status else None,
                    t.apple_music_status,
                    t.apple_music_import_file,
                    t.apple_music_error,
                )
            )
            if not submitted:
                raise RuntimeError("Conversion engine rejected the task")
            logger.info(f"Task {task_id} submitted to conversion engine")

            # 更新状态为转换中
            task.status = TaskStatus.CONVERTING
            # 保存任务到文件
            save_tasks()
        else:
            raise ValueError(f"Profile {task_create.profile_id} not found")
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task.end_time = datetime.now()
        save_tasks()
        logger.error(f"Failed to start conversion: {exc}")

    return task


@router.post("/", response_model=TaskResponse)
async def create_task(task_create: TaskCreate):
    """创建转换任务"""
    task = await enqueue_conversion_task(task_create)
    if task is None:
        raise HTTPException(status_code=409, detail="Task already exists")
    return task


@router.post("/batch-delete")
async def batch_delete_tasks(action: TaskBatchAction):
    """批量删除任务记录。"""
    task_ids = list(dict.fromkeys(action.task_ids))
    missing_ids = [task_id for task_id in task_ids if task_id not in tasks_cache]
    if missing_ids:
        raise HTTPException(status_code=404, detail="Some tasks were not found")

    delete_upload_links(task_ids)
    for task_id in task_ids:
        del tasks_cache[task_id]

    if task_ids:
        save_tasks()
        logger.info(f"Deleted {len(task_ids)} task records")

    return {"status": "success", "deleted": len(task_ids)}


def delete_upload_links(task_ids):
    """删除转换记录前检查上传状态，避免隐藏仍在执行的任务。"""
    from app.services.apple_music_upload import apple_music_upload_service
    uploads = [(task_id, apple_music_upload_service.for_task(task_id)) for task_id in task_ids
               if tasks_cache[task_id].apple_music_delivery_mode == "direct_upload"]
    if any(upload and not upload["can_delete"] for _, upload in uploads):
        raise HTTPException(409, "请先取消排队或停止关联上传，等待进程退出后再删除记录")
    for task_id, upload in uploads:
        if upload:
            apple_music_upload_service.delete(upload["id"], task_id)


async def submit_retry(task: TaskResponse) -> TaskResponse:
    """根据失败记录重新提交转换任务。"""
    new_task = await enqueue_conversion_task(TaskCreate(
        source_file=task.source_file,
        output_file=task.output_file,
        profile_id=task.profile_id,
    ))
    if new_task is None:
        raise HTTPException(status_code=409, detail="Task already exists")
    logger.info(f"Retrying task {task.id} as {new_task.id}")
    return new_task


def retry_apple_music_handoff(task: TaskResponse) -> TaskResponse:
    """仅重新交接已完成的转换成品，不重复执行编码。"""
    from app.services.apple_music_handoff import apple_music_handoff_service
    from app.services.profile_manager import profile_manager

    profile = profile_manager.get_profile(task.profile_id)
    if task.apple_music_delivery_mode == "direct_upload":
        raise HTTPException(status_code=400, detail="独立上传任务不能使用客户端交接重试")
    original_directory = str(Path(task.apple_music_import_file).parent) if task.apple_music_import_file else None
    if not original_directory and (not profile or not profile.apple_music_handoff_enabled):
        raise HTTPException(status_code=400, detail="原转换方案未启用 Apple Music 自动交接")
    directory = original_directory or profile.apple_music_import_dir
    if not directory:
        raise HTTPException(status_code=400, detail="原转换方案未配置 Apple Music 自动导入目录")

    try:
        task.apple_music_import_file = apple_music_handoff_service.handoff(
            task.output_file,
            directory,
        )
        task.apple_music_status = "waiting"
        task.apple_music_error = None
        logger.info(f"已重新交接 Apple Music 文件：{task.id}")
    except Exception as exc:
        task.apple_music_status = "failed"
        task.apple_music_error = str(exc)
        logger.error(f"重新交接 Apple Music 失败：{task.id}: {exc}")
        save_tasks()
        raise HTTPException(status_code=503, detail=f"Apple Music 交接失败：{exc}") from exc

    save_tasks()
    return task


@router.post("/batch-retry", response_model=List[TaskResponse])
async def batch_retry_tasks(action: TaskBatchAction):
    """批量重试失败任务。"""
    task_ids = list(dict.fromkeys(action.task_ids))
    missing_ids = [task_id for task_id in task_ids if task_id not in tasks_cache]
    if missing_ids:
        raise HTTPException(status_code=404, detail="Some tasks were not found")

    tasks = [tasks_cache[task_id] for task_id in task_ids]
    if any(task.status != TaskStatus.FAILED for task in tasks):
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    return [await submit_retry(task) for task in tasks]


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_cache[task_id]

    if task.status not in [TaskStatus.WAITING, TaskStatus.CONVERTING]:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")

    task.status = TaskStatus.CANCELLED
    task.end_time = datetime.now()

    logger.info(f"Cancelled task {task_id}")

    # 保存任务到文件
    save_tasks()

    return {"status": "success", "message": f"Task {task_id} cancelled"}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """重试任务"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_cache[task_id]

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    return await submit_retry(task)


@router.post("/{task_id}/retry-apple-music", response_model=TaskResponse)
async def retry_task_apple_music_handoff(task_id: str):
    """重试 Apple Music 交接，不重新转换文件。"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_cache[task_id]
    if task.apple_music_status not in {"failed", "received"}:
        raise HTTPException(status_code=400, detail="Only failed or received Apple Music handoffs can be retried")

    return retry_apple_music_handoff(task)


@router.get("/stats/summary")
async def get_task_stats():
    """获取任务统计"""
    stats = {
        "total": len(tasks_cache),
        "waiting": 0,
        "converting": 0,
        "success": 0,
        "failed": 0,
        "cancelled": 0,
    }

    for task in tasks_cache.values():
        stats[task.status.value] = stats.get(task.status.value, 0) + 1

    return stats
