"""统一入口应保存每个文件的目标，重扫不能追加另一库。"""
from app.models import DeliveryTarget, WatchFolder
from app.services.watch_routing import WatchRoutingService
import asyncio
import pytest
from pathlib import Path


@pytest.fixture
def routing(monkeypatch, tmp_path):
    service = WatchRoutingService(tmp_path / "routes.db")
    monkeypatch.setattr("app.services.watch_routing.watch_routing", service)
    monkeypatch.setattr("app.services.watch_folder_manager.watch_routing", service)
    return service


def make_folder(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "song.flac"
    source.write_bytes(b"audio")
    return WatchFolder(id="inbox", name="统一入口", input_dir=str(inbox), default_target="both", targets=[
        DeliveryTarget(type="copy", output_dir=str(tmp_path / "local")),
        DeliveryTarget(type="convert", profile_id="aac", output_dir=str(tmp_path / "apple")),
    ]), source


def test_explicit_target_survives_restart_and_default_change(tmp_path):
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")
    folder = WatchFolder(id="inbox", name="统一入口", input_dir=str(tmp_path), default_target="both", targets=[
        DeliveryTarget(type="copy", output_dir=str(tmp_path / "local")),
        DeliveryTarget(type="convert", profile_id="aac", output_dir=str(tmp_path / "apple")),
    ])
    service = WatchRoutingService(tmp_path / "routes.db")
    plan = service.register(folder, source, source, True, False)
    folder.default_target = "apple"
    restarted = WatchRoutingService(tmp_path / "routes.db")
    assert restarted.get(folder.id, source) == plan
    assert [item["library"] for item in plan["outputs"]] == ["nas"]


def test_replaced_file_gets_new_plan(tmp_path):
    source = tmp_path / "song.flac"
    source.write_bytes(b"one")
    folder = WatchFolder(id="inbox", name="入口", input_dir=str(tmp_path))
    service = WatchRoutingService(tmp_path / "routes.db")
    service.register(folder, source, source, True, False)
    source.write_bytes(b"different audio")
    assert service.get(folder.id, source) is None


def test_plan_is_saved_before_file_becomes_visible(tmp_path):
    temporary = tmp_path / "song.part"
    final = tmp_path / "song.flac"
    temporary.write_bytes(b"audio")
    folder = WatchFolder(id="inbox", name="入口", input_dir=str(tmp_path))
    service = WatchRoutingService(tmp_path / "routes.db")
    plan = service.register(folder, final, temporary, False, True)
    temporary.replace(final)
    assert service.get(folder.id, final) == plan


def test_local_only_never_uploads_even_after_default_change(monkeypatch, tmp_path, routing):
    """发现页选择仅本地，不能被目录默认目标或重扫追加上传。"""
    from app.services.watch_folder_manager import WatchFolderManager
    folder, source = make_folder(tmp_path)
    routing.register(folder, source, source, True, False)
    monkeypatch.setattr("app.services.media_library_service.media_library_service.index_output", lambda _path: True)
    monkeypatch.setattr("app.services.acquisition_service.acquisition_service.mark_nas_delivered", lambda *_args: None)
    manager = WatchFolderManager()
    first = asyncio.run(manager._process_file(folder, str(source), "test"))
    folder.default_target = "apple"
    second = asyncio.run(WatchFolderManager()._process_file(folder, str(source), "rescan"))
    assert first == {"created_tasks": 0, "copied_files": 1}
    assert second == {"created_tasks": 0, "copied_files": 0}
    assert not (tmp_path / "apple").exists()


def test_one_target_failure_does_not_stop_other_target(monkeypatch, tmp_path, routing):
    """本地复制失败仍应提交 Apple Music，重复扫描不重新提交。"""
    from app.api.routes import tasks
    from app.models import Profile
    from app.services.watch_folder_manager import WatchFolderManager
    folder, source = make_folder(tmp_path)
    routing.register(folder, source, source, True, True)
    profile = Profile(id="aac", name="上传", output_format="m4a", apple_music_delivery_mode="direct_upload")
    monkeypatch.setattr("app.services.profile_manager.profile_manager.get_profile", lambda _id: profile)
    monkeypatch.setattr(tasks, "tasks_cache", {})
    queued = []

    async def enqueue(request, skip_existing=False):
        queued.append(request)
        task = tasks.TaskResponse(id="conversion", **request.model_dump(), status="waiting")
        tasks.tasks_cache[task.id] = task
        return task

    def fail_copy(*_args):
        raise PermissionError("模拟本地目录无权限")

    monkeypatch.setattr(tasks, "enqueue_conversion_task", enqueue)
    manager = WatchFolderManager()
    monkeypatch.setattr(manager, "_copy_file", fail_copy)
    asyncio.run(manager._process_file(folder, str(source), "test"))
    asyncio.run(manager._process_file(folder, str(source), "rescan"))
    outputs = routing.get(folder.id, source)["outputs"]
    assert [item["state"] for item in outputs] == ["failed", "submitted"]
    assert len(queued) == 1


def test_external_file_without_metadata_waits_for_confirmation(monkeypatch, tmp_path, routing):
    """外部文件不能在缺少身份信息时盲目上传。"""
    from app.services.watch_folder_manager import WatchFolderManager
    folder, source = make_folder(tmp_path)
    monkeypatch.setattr("app.core.metadata_service.read_metadata", lambda _path: {})
    result = asyncio.run(WatchFolderManager()._process_file(folder, str(source), "test"))
    assert result == {"created_tasks": 0, "copied_files": 0}
    assert routing.get(folder.id, source)["review"]


def test_unified_acquisition_places_one_source_and_registers_target(monkeypatch, tmp_path, routing):
    """双库任务只向统一入口投递一次，并在文件可见前保存目标。"""
    from app.services.acquisition_service import AcquisitionService
    from app.services.watch_folder_manager import watch_folder_manager
    folder, source = make_folder(tmp_path)
    original = tmp_path / "original.flac"
    original.write_bytes(b"downloaded")
    service = AcquisitionService(tmp_path / "routes.db")
    monkeypatch.setattr(service, "start", lambda _id: None)
    monkeypatch.setattr("app.services.dual_library_config.dual_library_config.resolve", lambda: {"unified_watch_folder_id": folder.id})
    monkeypatch.setattr(watch_folder_manager, "get_watch_folder", lambda _id: folder)
    job = service.create_job(None, "local", str(original), True, True)
    service._run(job["id"])
    delivered = service.get_job(job["id"])
    assert delivered["nas_path"] == delivered["apple_watch_path"]
    assert len(list(source.parent.glob("original*"))) == 1
    plan = routing.get(folder.id, Path(delivered["nas_path"]))
    assert plan["nas"] and plan["apple"]
    assert delivered["status"] == "processing"


def test_external_dual_fill_skips_present_libraries(monkeypatch, tmp_path, routing):
    """两边已有时只登记跳过，不创建输出任务。"""
    folder, source = make_folder(tmp_path)
    monkeypatch.setattr("app.core.metadata_service.read_metadata", lambda _path: {"title": "歌曲", "artist": "歌手", "album": "专辑"})
    monkeypatch.setattr("app.services.media_library_service.media_library_service.load_tracks", lambda _refresh: [])
    monkeypatch.setattr("app.services.dual_library_service.dual_library_service.build_presence_index", lambda _tracks: {})
    monkeypatch.setattr("app.services.dual_library_service.dual_library_service.lookup_presence", lambda *_args: {"nas_present": True, "apple_present": True})
    assert routing.plan(folder, source)["outputs"] == []


def test_manual_add_second_library_preserves_submitted_outputs(tmp_path):
    folder, source = make_folder(tmp_path)
    service = WatchRoutingService(tmp_path / "routes.db")
    plan = service.register(folder, source, source, True, False)
    plan["outputs"][0]["state"] = "success"
    service.save(folder.id, source, plan)
    updated = service.register(folder, source, source, True, True, replace=True)
    assert [item["state"] for item in updated["outputs"]] == ["success", "waiting"]


def test_migrating_legacy_folder_requires_confirmation_for_old_files(monkeypatch, tmp_path, routing):
    """旧目录切换模式时，不对稳定历史文件套用新默认目标。"""
    from app.services.watch_folder_manager import WatchFolderManager
    folder, source = make_folder(tmp_path)
    old = folder.model_copy(update={"default_target": "all"})
    manager = WatchFolderManager()
    manager.watch_folders = {folder.id: old}
    monkeypatch.setattr(manager, "_scan_directory", lambda *_args: [str(source)])
    monkeypatch.setattr(manager, "save_watch_folders", lambda: None)
    monkeypatch.setattr(manager, "_start_watching", lambda _folder: None)
    monkeypatch.setattr("app.services.watch_folder_manager.watcher_service.stop_watch", lambda _path: None)
    manager.update_watch_folder(folder.id, folder)
    assert routing.get(folder.id, source)["review"] == "旧目录历史文件，请选择目标后确认处理"


def test_retry_only_requeues_failed_output(monkeypatch, tmp_path, routing):
    """重试失败的 Apple Music 转换不能再复制已成功的本地目标。"""
    from app.api.routes import tasks
    from app.services.acquisition_service import AcquisitionService
    from app.services.watch_folder_manager import watch_folder_manager
    folder, source = make_folder(tmp_path)
    plan = routing.register(folder, source, source, True, True)
    plan["outputs"][0]["state"] = "success"
    plan["outputs"][1].update(state="submitted", task_id="failed-task")
    failed = tasks.TaskResponse(id="failed-task", source_file=str(source), output_file=str(tmp_path / 'apple/song.m4a'), profile_id="aac", status="failed")
    monkeypatch.setattr(tasks, "tasks_cache", {failed.id: failed})
    calls = []

    async def retry(task_id):
        calls.append(task_id)
        return failed.model_copy(update={"id": "retried-task"})

    async def process(_folder, _path, _trigger):
        return {"copied_files": 0, "created_tasks": 0}

    monkeypatch.setattr(tasks, "retry_task", retry)
    monkeypatch.setattr("app.services.apple_music_upload.apple_music_upload_service.for_task", lambda _id: None)
    monkeypatch.setattr(watch_folder_manager, "get_watch_folder", lambda _id: folder)
    monkeypatch.setattr(watch_folder_manager, "_process_file", process)
    asyncio.run(AcquisitionService(tmp_path / "routes.db")._retry_routed_outputs(folder.id, plan))
    assert calls == ["failed-task"]
    saved = routing.get(folder.id, source)
    assert saved["outputs"][0]["state"] == "success"
    assert saved["outputs"][1]["task_id"] == "retried-task"


def test_same_song_pending_job_is_reused(monkeypatch, tmp_path):
    """多音源结果重复点击同一首歌时，应沿用已有的本地任务。"""
    from app.services.acquisition_service import AcquisitionService
    service = AcquisitionService(tmp_path / "routes.db")
    monkeypatch.setattr(service, "start", lambda _id: None)
    track = {"song_name": "歌曲", "singers": "歌手", "album": "专辑", "token": "first-source"}
    first = service.create_job(track, None, None, True, False)
    second = service.create_job({**track, "token": "other-source"}, None, None, True, False)
    assert first["id"] == second["id"]
    with pytest.raises(ValueError, match="已有处理中的任务"):
        service.create_job(track, None, None, True, True)


def test_unified_configuration_saves_single_watch_folder(monkeypatch, tmp_path):
    """双库设置允许关联含两个目标的同一个入口。"""
    from app.api.routes import discovery
    from app.models import Profile
    folder, _source = make_folder(tmp_path)
    profile = Profile(id="aac", name="上传", output_format="m4a", apple_music_delivery_mode="direct_upload")
    monkeypatch.setattr(discovery.watch_folder_manager, "get_watch_folder", lambda _id: folder)
    monkeypatch.setattr(discovery.profile_manager, "get_profile", lambda _id: profile)
    saved = []
    monkeypatch.setattr(discovery.dual_library_config, "save", lambda *args: saved.append(args) or {})
    asyncio.run(discovery.update_dual_library_config(discovery.DualLibraryConfigRequest(unified_watch_folder_id=folder.id)))
    assert saved == [("", "", "cn", folder.id)]


def test_manual_routing_rejects_path_outside_inbox(monkeypatch, tmp_path):
    """手动补齐接口不能读取监控目录之外的任意文件。"""
    from app.api.routes import watch_folders
    from fastapi import HTTPException
    folder, _source = make_folder(tmp_path)
    outside = tmp_path / "outside.flac"
    outside.write_bytes(b"audio")
    monkeypatch.setattr(watch_folders.watch_folder_manager, "get_watch_folder", lambda _id: folder)
    with pytest.raises(HTTPException) as error:
        asyncio.run(watch_folders.process_routed_file(folder.id, watch_folders.FileRoutingRequest(path=str(outside), target="both")))
    assert error.value.status_code == 400
