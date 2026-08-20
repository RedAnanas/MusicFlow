import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.routes import tasks as tasks_api


def make_task(
    task_id: str,
    status: tasks_api.TaskStatus,
    start_time: datetime | None,
) -> tasks_api.TaskResponse:
    """创建任务 API 测试数据。"""
    return tasks_api.TaskResponse(
        id=task_id,
        source_file=f"/source/{task_id}.flac",
        output_file=f"/output/{task_id}.m4a",
        profile_id="profile-1",
        status=status,
        start_time=start_time,
    )


@pytest.fixture(autouse=True)
def clear_tasks_cache():
    """隔离每个测试使用的任务缓存。"""
    original_tasks = dict(tasks_api.tasks_cache)
    tasks_api.tasks_cache.clear()
    yield
    tasks_api.tasks_cache.clear()
    tasks_api.tasks_cache.update(original_tasks)


def test_get_tasks_returns_newest_records_first():
    """任务列表应先排序再限制数量，且无时间记录排在最后。"""
    now = datetime.now()
    tasks_api.tasks_cache.update({
        "old": make_task("old", tasks_api.TaskStatus.SUCCESS, now - timedelta(days=1)),
        "missing-time": make_task("missing-time", tasks_api.TaskStatus.SUCCESS, None),
        "new": make_task("new", tasks_api.TaskStatus.FAILED, now),
        "middle": make_task("middle", tasks_api.TaskStatus.SUCCESS, now - timedelta(hours=1)),
    })

    result = asyncio.run(tasks_api.get_tasks(status=None, limit=3))

    assert [task.id for task in result] == ["new", "middle", "old"]


def test_get_tasks_marks_missing_import_file_as_received(monkeypatch):
    """自动导入文件消失后，任务应标记为 Apple Music 已接收。"""
    task = make_task("apple-music", tasks_api.TaskStatus.SUCCESS, datetime.now())
    task.apple_music_status = "waiting"
    task.apple_music_import_file = "/missing/歌曲.m4a"
    tasks_api.tasks_cache[task.id] = task
    saved = []

    monkeypatch.setattr(tasks_api, "save_tasks", lambda: saved.append(True))
    monkeypatch.setattr(
        "app.services.apple_music_handoff.apple_music_handoff_service.is_received",
        lambda _path: True,
    )

    result = asyncio.run(tasks_api.get_tasks(status=None, limit=100))

    assert result[0].apple_music_status == "received"
    assert saved == [True]


@pytest.mark.parametrize("status", list(tasks_api.TaskStatus))
def test_delete_task_allows_every_status(monkeypatch, status):
    """每一种任务状态都允许删除记录。"""
    task = make_task("task-1", status, datetime.now())
    tasks_api.tasks_cache[task.id] = task
    save_calls = []
    monkeypatch.setattr(tasks_api, "save_tasks", lambda: save_calls.append(True))

    result = asyncio.run(tasks_api.delete_task(task.id))

    assert result == {"status": "success", "deleted": 1}
    assert task.id not in tasks_api.tasks_cache
    assert save_calls == [True]


def test_batch_delete_removes_selected_records_once(monkeypatch):
    """批量删除应一次保存并返回实际删除数量。"""
    tasks_api.tasks_cache.update({
        "task-1": make_task("task-1", tasks_api.TaskStatus.SUCCESS, datetime.now()),
        "task-2": make_task("task-2", tasks_api.TaskStatus.FAILED, datetime.now()),
    })
    save_calls = []
    monkeypatch.setattr(tasks_api, "save_tasks", lambda: save_calls.append(True))

    result = asyncio.run(tasks_api.batch_delete_tasks(
        tasks_api.TaskBatchAction(task_ids=["task-1", "task-2", "task-1"])
    ))

    assert result == {"status": "success", "deleted": 2}
    assert tasks_api.tasks_cache == {}
    assert save_calls == [True]


def test_batch_retry_submits_each_failed_task(monkeypatch):
    """批量重试应为每条失败记录重新提交转换任务。"""
    tasks_api.tasks_cache.update({
        "failed-1": make_task("failed-1", tasks_api.TaskStatus.FAILED, datetime.now()),
        "failed-2": make_task("failed-2", tasks_api.TaskStatus.FAILED, datetime.now()),
    })
    submitted = []

    async def fake_enqueue(task_create):
        submitted.append(task_create)
        return make_task(
            f"retry-{len(submitted)}",
            tasks_api.TaskStatus.WAITING,
            datetime.now(),
        )

    monkeypatch.setattr(tasks_api, "enqueue_conversion_task", fake_enqueue)

    result = asyncio.run(tasks_api.batch_retry_tasks(
        tasks_api.TaskBatchAction(task_ids=["failed-1", "failed-2"])
    ))

    assert [task.id for task in result] == ["retry-1", "retry-2"]
    assert [task.source_file for task in submitted] == [
        "/source/failed-1.flac",
        "/source/failed-2.flac",
    ]


def test_batch_retry_rejects_non_failed_task(monkeypatch):
    """批量重试包含非失败任务时不应提交任何新任务。"""
    tasks_api.tasks_cache["success"] = make_task(
        "success",
        tasks_api.TaskStatus.SUCCESS,
        datetime.now(),
    )
    submitted = []

    async def fake_enqueue(task_create):
        submitted.append(task_create)
        return None

    monkeypatch.setattr(tasks_api, "enqueue_conversion_task", fake_enqueue)

    with pytest.raises(HTTPException) as error:
        asyncio.run(tasks_api.batch_retry_tasks(
            tasks_api.TaskBatchAction(task_ids=["success"])
        ))

    assert error.value.status_code == 400
    assert submitted == []
