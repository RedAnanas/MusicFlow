import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import files as files_api
from app.api.routes import tasks as tasks_api
from app.models import OutputFormat, Profile, TaskStatus
from app.services.profile_manager import profile_manager


@pytest.fixture(autouse=True)
def restore_files_cache():
    """隔离每个测试使用的文件缓存。"""
    original_files = dict(files_api.files_cache)
    files_api.files_cache.clear()
    yield
    files_api.files_cache.clear()
    files_api.files_cache.update(original_files)


def test_delete_file_removes_source_file(monkeypatch, tmp_path):
    """删除接口应移除音乐源目录内的文件和缓存。"""
    source_dir = tmp_path / "source"
    source_file = source_dir / "album" / "song.flac"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"audio")
    monkeypatch.setattr(files_api.settings, "MUSIC_SOURCE_DIR", str(source_dir))
    files_api.files_cache["file-1"] = {
        "path": str(source_file),
        "filename": source_file.name,
    }

    result = asyncio.run(files_api.delete_file("file-1"))

    assert result == {"status": "success", "deleted": "file-1"}
    assert not source_file.exists()
    assert "file-1" not in files_api.files_cache


def test_delete_file_rejects_path_outside_source_directory(monkeypatch, tmp_path):
    """删除接口不得删除音乐源目录之外的文件。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    outside_file = tmp_path / "outside.flac"
    outside_file.write_bytes(b"audio")
    monkeypatch.setattr(files_api.settings, "MUSIC_SOURCE_DIR", str(source_dir))
    files_api.files_cache["outside"] = {
        "path": str(outside_file),
        "filename": outside_file.name,
    }

    with pytest.raises(HTTPException) as error:
        asyncio.run(files_api.delete_file("outside"))

    assert error.value.status_code == 403
    assert outside_file.exists()


def test_convert_file_creates_task_with_optional_output_directory(monkeypatch, tmp_path):
    """单个转换应使用可选输出目录创建真实任务。"""
    source_file = tmp_path / "source" / "song.flac"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"audio")
    output_dir = tmp_path / "output"
    files_api.files_cache["file-1"] = {"path": str(source_file), "filename": source_file.name}
    profile = Profile(id="aac", name="AAC", output_format=OutputFormat.M4A)
    monkeypatch.setattr(profile_manager, "get_profile", lambda _id: profile)
    captured = []

    async def enqueue(task_create, skip_existing):
        captured.append((task_create, skip_existing))
        return tasks_api.TaskResponse(
            id="task-1",
            source_file=task_create.source_file,
            output_file=task_create.output_file,
            profile_id=task_create.profile_id,
            status=TaskStatus.WAITING,
        )

    monkeypatch.setattr(tasks_api, "enqueue_conversion_task", enqueue)

    result = asyncio.run(files_api.convert_file(
        "file-1",
        files_api.FileConvertRequest(profile_id="aac", output_dir=str(output_dir)),
    ))

    assert result["converted"][0] == {
        "status": "queued",
        "output_file": str(output_dir / "song.m4a"),
        "task_id": "task-1",
    }
    assert captured[0][1] is True


def test_batch_convert_returns_missing_file_errors(monkeypatch, tmp_path):
    """批量转换应提交有效文件并返回不存在文件的错误。"""
    source_file = tmp_path / "song.flac"
    source_file.write_bytes(b"audio")
    files_api.files_cache["file-1"] = {"path": str(source_file), "filename": source_file.name}

    async def queue(file_id, _request):
        if file_id == "missing":
            raise HTTPException(status_code=404, detail="File not found")
        return {"status": "queued", "output_file": "/output/song.m4a", "task_id": file_id}

    monkeypatch.setattr(files_api, "queue_file_conversion", queue)

    result = asyncio.run(files_api.batch_convert_files(
        files_api.FileBatchConvertRequest(profile_id="aac", file_ids=["file-1", "missing"]),
    ))

    assert result["converted"] == [{
        "file_id": "file-1",
        "status": "queued",
        "output_file": "/output/song.m4a",
        "task_id": "file-1",
    }]
    assert result["errors"] == [{"file_id": "missing", "error": "File not found"}]
