import logging
import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

router = APIRouter()
logger = logging.getLogger(__name__)

# 任务存储（内存缓存）
tasks_cache: dict = {}


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


# 进度回调函数 - 更新 tasks_cache 中的任务状态
def update_task_progress(task_id: str, progress: float, status: str = None):
    """更新任务进度"""
    if task_id in tasks_cache:
        task = tasks_cache[task_id]
        task.progress = progress
        if status:
            task.status = status
        if status in ['success', 'failed', 'cancelled']:
            task.end_time = datetime.now()
        logger.info(f"Task {task_id} progress: {progress}%, status: {status}")


@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    status: Optional[TaskStatus] = Query(None, description="状态筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制")
):
    """获取所有任务"""
    tasks = list(tasks_cache.values())

    # 状态筛选
    if status:
        tasks = [t for t in tasks if t.status == status]

    # 限制返回数量
    return tasks[:limit]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取单个任务详情"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    return tasks_cache[task_id]


@router.post("/", response_model=TaskResponse)
async def create_task(task_create: TaskCreate):
    """创建转换任务"""
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

    # 自动触发转换引擎执行任务
    try:
        from app.services.conversion_engine import conversion_engine
        from app.services.profile_manager import profile_manager
        from app.models import Task, Profile, TaskStatus as ModelTaskStatus

        # 获取 Profile
        profile = profile_manager.get_profile(task_create.profile_id)
        if profile:
            # 创建模型任务
            model_task = Task(
                id=task_id,
                source_file=task_create.source_file,
                output_file=task_create.output_file,
                profile_id=task_create.profile_id,
                status=ModelTaskStatus.WAITING,
                start_time=datetime.now(),
            )

            # 提交到转换引擎，传入进度回调
            await conversion_engine.submit_task(
                model_task,
                profile,
                progress_callback=lambda t: update_task_progress(
                    t.id,
                    t.progress or 0,
                    t.status.value if t.status else None
                )
            )
            logger.info(f"Task {task_id} submitted to conversion engine")

            # 更新状态为转换中
            task.status = TaskStatus.CONVERTING
        else:
            logger.warning(f"Profile {task_create.profile_id} not found")
    except Exception as e:
        logger.error(f"Failed to start conversion: {e}")

    return task


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

    return {"status": "success", "message": f"Task {task_id} cancelled"}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """重试任务"""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_cache[task_id]

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    # 创建新任务
    new_task_id = str(uuid.uuid4())
    new_task = TaskResponse(
        id=new_task_id,
        source_file=task.source_file,
        output_file=task.output_file,
        profile_id=task.profile_id,
        status=TaskStatus.WAITING,
        start_time=datetime.now(),
    )

    tasks_cache[new_task_id] = new_task

    logger.info(f"Retrying task {task_id} as {new_task_id}")

    return new_task


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
