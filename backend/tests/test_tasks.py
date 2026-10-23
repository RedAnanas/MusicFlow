import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from fastapi import HTTPException

from app.api.routes import tasks as tasks_api
from app.services import profile_manager as profile_manager_module


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


def test_任务列表只刷新筛选并限制后的上传记录而详情只刷新当前任务(monkeypatch):
    from app.services.apple_music_upload import apple_music_upload_service

    now = datetime.now()
    for index in range(3):
        task = make_task(str(index), tasks_api.TaskStatus.SUCCESS, now + timedelta(seconds=index))
        task.apple_music_delivery_mode = 'direct_upload'
        tasks_api.tasks_cache[task.id] = task
    refreshed = []

    def for_tasks(task_ids, summary=False):
        refreshed.append((list(task_ids), summary))
        return {}

    monkeypatch.setattr(apple_music_upload_service, 'for_tasks', for_tasks)
    result = asyncio.run(tasks_api.get_tasks(status=tasks_api.TaskStatus.SUCCESS, limit=1, summary=True))
    assert [task.id for task in result] == ['2']
    assert refreshed == [(['2'], True)]
    asyncio.run(tasks_api.get_task('0'))
    assert refreshed[-1] == (['0'], False)


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


def test_get_tasks_marks_unavailable_import_directory_as_failed(monkeypatch):
    """挂载目录不可访问时不能把文件消失误判为 Apple Music 已接收。"""
    task = make_task("apple-music", tasks_api.TaskStatus.SUCCESS, datetime.now())
    task.apple_music_status = "waiting"
    task.apple_music_import_file = "/unavailable/歌曲.m4a"
    tasks_api.tasks_cache[task.id] = task
    saved = []

    monkeypatch.setattr(tasks_api, "save_tasks", lambda: saved.append(True))

    def raise_unavailable(_path):
        raise OSError("Apple Music 自动导入目录不可访问")

    monkeypatch.setattr(
        "app.services.apple_music_handoff.apple_music_handoff_service.is_received",
        raise_unavailable,
    )

    result = asyncio.run(tasks_api.get_tasks(status=None, limit=100))

    assert result[0].apple_music_status == "failed"
    assert result[0].apple_music_error == "Apple Music 自动导入目录不可访问"
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


def test_retry_apple_music_handoff_reuses_converted_file(monkeypatch, tmp_path):
    """交接重试只复制既有成品，不重新提交转换任务。"""
    output_file = tmp_path / "歌曲.m4a"
    output_file.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"
    import_dir.mkdir()
    task = make_task("apple-music", tasks_api.TaskStatus.SUCCESS, datetime.now())
    task.output_file = str(output_file)
    task.apple_music_status = "failed"
    tasks_api.tasks_cache[task.id] = task
    saved = []

    class Profile:
        apple_music_handoff_enabled = True
        apple_music_import_dir = str(import_dir)

    monkeypatch.setattr(tasks_api, "save_tasks", lambda: saved.append(True))
    monkeypatch.setattr(profile_manager_module.profile_manager, "get_profile", lambda _profile_id: Profile())

    result = asyncio.run(tasks_api.retry_task_apple_music_handoff(task.id))

    assert result.apple_music_status == "waiting"
    assert result.apple_music_error is None
    assert (import_dir / output_file.name).read_bytes() == b"music-data"
    assert saved == [True]


def test_retry_apple_music_handoff_records_unavailable_directory(monkeypatch, tmp_path):
    """交接目录不可用时应保留失败状态和原因。"""
    task = make_task("apple-music", tasks_api.TaskStatus.SUCCESS, datetime.now())
    task.output_file = str(tmp_path / "missing.m4a")
    task.apple_music_status = "failed"
    tasks_api.tasks_cache[task.id] = task
    saved = []

    class Profile:
        apple_music_handoff_enabled = True
        apple_music_import_dir = str(tmp_path / "Automatically Add to Apple Music")

    monkeypatch.setattr(profile_manager_module.profile_manager, "get_profile", lambda _profile_id: Profile())
    monkeypatch.setattr(tasks_api, "save_tasks", lambda: saved.append(True))

    with pytest.raises(HTTPException) as error:
        asyncio.run(tasks_api.retry_task_apple_music_handoff(task.id))

    assert error.value.status_code == 503
    assert task.apple_music_status == "failed"
    assert "转换成品不存在" in (task.apple_music_error or "")
    assert saved == [True]


def test_retry_apple_music_handoff_allows_received_record(monkeypatch):
    """误判为已接收的记录应允许用户手动再次交接。"""
    task = make_task("apple-music", tasks_api.TaskStatus.SUCCESS, datetime.now())
    task.apple_music_status = "received"
    tasks_api.tasks_cache[task.id] = task
    retried = []

    def fake_retry(received_task):
        retried.append(received_task.id)
        return received_task

    monkeypatch.setattr(tasks_api, "retry_apple_music_handoff", fake_retry)

    result = asyncio.run(tasks_api.retry_task_apple_music_handoff(task.id))

    assert result.id == task.id
    assert retried == [task.id]


def test_任务时间接口必须包含时区以免浏览器错算八小时():
    task = make_task('timezone', tasks_api.TaskStatus.SUCCESS, datetime(2026,10,17,5,28,13))
    task.end_time = datetime(2026,10,17,5,28,27)
    payload = task.model_dump(mode='json')
    parsed_start = datetime.fromisoformat(payload['start_time'])
    parsed_end = datetime.fromisoformat(payload['end_time'])
    assert parsed_start.tzinfo is not None
    assert parsed_end.tzinfo is not None
    assert parsed_start.timestamp() == task.start_time.timestamp()
    assert parsed_end.timestamp() - parsed_start.timestamp() == 14


def test_已经带时区的任务不重复偏移():
    from datetime import timezone
    task = make_task('aware', tasks_api.TaskStatus.SUCCESS, datetime(2026,10,17,5,28,13,tzinfo=timezone.utc))
    payload = task.model_dump(mode='json')
    start = datetime.fromisoformat(payload['start_time'])
    finish = datetime(2026,10,17,13,44,50,tzinfo=timezone(timedelta(hours=8)))
    assert (finish-start).total_seconds() == 16*60+37


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_任务保存失败保留原文件并清理临时文件(monkeypatch, tmp_path, caplog, failure):
    tasks_file = tmp_path / "tasks.json"
    original = {"old": make_task("old", tasks_api.TaskStatus.SUCCESS, None).model_dump(mode="json")}
    tasks_file.write_text(json.dumps(original), encoding="utf-8")
    tasks_api.tasks_cache["new"] = make_task("new", tasks_api.TaskStatus.SUCCESS, None)
    monkeypatch.setattr(tasks_api, "TASKS_FILE", tasks_file)

    def fail_write(_data, output, **_kwargs):
        output.write('{"partial":')
        raise OSError("模拟写入失败")

    def fail_replace(_source, _target):
        raise OSError("模拟替换失败")

    if failure == "write":
        monkeypatch.setattr(tasks_api.json, "dump", fail_write)
    else:
        monkeypatch.setattr(Path, "replace", fail_replace)

    tasks_api.save_tasks()

    assert json.loads(tasks_file.read_text(encoding="utf-8")) == original
    assert list(tmp_path.iterdir()) == [tasks_file]
    assert "Error saving tasks" in caplog.text


def test_并发保存串行写入且原文件在替换前保持完整(monkeypatch, tmp_path):
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text("{}", encoding="utf-8")
    task = make_task("concurrent", tasks_api.TaskStatus.SUCCESS, datetime.now())
    tasks_api.tasks_cache[task.id] = task
    monkeypatch.setattr(tasks_api, "TASKS_FILE", tasks_file)
    first_entered, release_first, second_started, second_entered = (Event() for _ in range(4))
    original_dump = json.dump

    def delayed_dump(data, output, **kwargs):
        if not first_entered.is_set():
            output.write('{"partial":')
            first_entered.set()
            assert release_first.wait(5), "首个写入未被释放"
            output.seek(0)
            output.truncate()
        else:
            second_entered.set()
        original_dump(data, output, **kwargs)

    def second_save():
        second_started.set()
        tasks_api.save_tasks()

    monkeypatch.setattr(tasks_api.json, "dump", delayed_dump)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(tasks_api.save_tasks)
        try:
            assert first_entered.wait(5)
            second = executor.submit(second_save)
            assert second_started.wait(5)
            assert not second_entered.wait(0.1), "两个保存操作同时进入写入阶段"
            assert json.loads(tasks_file.read_text(encoding="utf-8")) == {}
        finally:
            release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert second_entered.is_set()
    saved = json.loads(tasks_file.read_text(encoding="utf-8"))
    assert saved[task.id] == task.model_dump(mode="json")
    tasks_api.tasks_cache.clear()
    tasks_api.load_tasks()
    assert tasks_api.tasks_cache[task.id].start_time.timestamp() == task.start_time.timestamp()
    assert list(tmp_path.iterdir()) == [tasks_file]
