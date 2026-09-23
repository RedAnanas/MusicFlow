from pathlib import Path

from app.services.acquisition_service import AcquisitionService
from app.models import WatchFolder
from app.services.dual_library_config import dual_library_config
from app.services.watch_folder_manager import watch_folder_manager


def test_create_job_persists_per_destination_status(monkeypatch, tmp_path: Path) -> None:
    """补齐任务应持久化两个目标的独立状态。"""
    service = AcquisitionService(tmp_path / "musicflow.db")
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    monkeypatch.setattr(service, "start", lambda _job_id: None)

    job = service.create_job(None, "local-1", str(source), False, True)
    restarted = AcquisitionService(tmp_path / "musicflow.db").get_job(job["id"])

    assert restarted["nas_status"] == "not_needed"
    assert restarted["apple_status"] == "waiting"
    assert restarted["local_file_id"] == "local-1"


def test_local_job_submits_source_to_watch_folder(monkeypatch, tmp_path: Path) -> None:
    """补齐任务应进入下载监控目录，不能直接写入最终媒体库。"""
    service = AcquisitionService(tmp_path / "musicflow.db")
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()
    folder = WatchFolder(id="downloads", name="下载目录", input_dir=str(target_dir))
    monkeypatch.setattr(dual_library_config, "resolve", lambda: {
        "nas_watch_folder_id": folder.id,
        "apple_watch_folder_id": "",
    })
    monkeypatch.setattr(watch_folder_manager, "get_watch_folder", lambda _folder_id: folder)
    monkeypatch.setattr(service, "start", lambda _job_id: None)
    job = service.create_job(None, "local-1", str(source), True, False)

    service._run(job["id"])
    completed = service.get_job(job["id"])

    assert completed["status"] == "completed"
    assert completed["nas_status"] == "submitted"
    assert completed["apple_status"] == "not_needed"
    assert (target_dir / "source.flac").read_bytes() == b"audio"


def test_nas_job_becomes_present_only_after_copy_output(monkeypatch, tmp_path: Path) -> None:
    """提交监控目录不能算已入库，复制到整理媒体库后才更新飞牛状态。"""
    service = AcquisitionService(tmp_path / "musicflow.db")
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()
    folder = WatchFolder(id="downloads", name="下载目录", input_dir=str(target_dir))
    monkeypatch.setattr(dual_library_config, "resolve", lambda: {
        "nas_watch_folder_id": folder.id,
        "apple_watch_folder_id": "",
    })
    monkeypatch.setattr(watch_folder_manager, "get_watch_folder", lambda _folder_id: folder)
    monkeypatch.setattr(service, "start", lambda _job_id: None)
    job = service.create_job(None, "local-1", str(source), True, False)
    service._run(job["id"])
    submitted = service.get_job(job["id"])
    output = tmp_path / "library" / "source.flac"
    output.parent.mkdir()
    output.write_bytes(b"audio")

    assert submitted["nas_status"] == "submitted"
    service.mark_nas_delivered(submitted["nas_path"], output)
    assert service.get_job(job["id"])["nas_status"] == "success"


def test_job_routes_each_missing_library_to_its_own_watch_folder(monkeypatch, tmp_path: Path) -> None:
    """双库都缺失时应只下载一次，并分别投递到两个独立监控目录。"""
    service = AcquisitionService(tmp_path / "musicflow.db")
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    nas_dir = tmp_path / "nas-downloads"
    apple_dir = tmp_path / "apple-downloads"
    nas_dir.mkdir()
    apple_dir.mkdir()
    folders = {
        "nas": WatchFolder(id="nas", name="飞牛", input_dir=str(nas_dir)),
        "apple": WatchFolder(id="apple", name="AM", input_dir=str(apple_dir)),
    }
    monkeypatch.setattr(dual_library_config, "resolve", lambda: {
        "nas_watch_folder_id": "nas",
        "apple_watch_folder_id": "apple",
    })
    monkeypatch.setattr(watch_folder_manager, "get_watch_folder", folders.get)
    monkeypatch.setattr(service, "start", lambda _job_id: None)
    monkeypatch.setattr(
        "app.services.acquisition_service.dual_library_service.upsert_incremental_track",
        lambda *_args, **_kwargs: {},
    )
    job = service.create_job(
        {"song_name": "歌曲", "singers": "歌手", "album": "专辑"},
        None,
        str(source),
        True,
        True,
    )

    service._run(job["id"])
    completed = service.get_job(job["id"])

    assert completed["nas_status"] == "submitted"
    assert completed["apple_status"] == "submitted"
    assert (nas_dir / "source.flac").read_bytes() == b"audio"
    assert (apple_dir / "source.flac").read_bytes() == b"audio"


def test_partial_job_retries_only_failed_target(monkeypatch, tmp_path: Path) -> None:
    """部分失败后重试应保留已成功目标，只重新执行失败目标。"""
    service = AcquisitionService(tmp_path / "musicflow.db")
    source = tmp_path / "source.flac"
    source.write_bytes(b"audio")
    monkeypatch.setattr(service, "start", lambda _job_id: None)
    job = service.create_job(None, "local-1", str(source), True, True)
    service._update(job["id"], status="partial", nas_status="success", apple_status="failed")

    retried = service.retry(job["id"])

    assert retried["nas_status"] == "success"
    assert retried["apple_status"] == "waiting"
    assert retried["status"] == "queued"
