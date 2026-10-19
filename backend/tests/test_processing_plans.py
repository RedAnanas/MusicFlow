"""处理方案在监控、操作台和本地资料库补齐之间复用。"""
import asyncio
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import discovery, files, tasks, watch_folders
from app.core import metadata_service
from app.models import DeliveryTarget, Profile, Task, WatchFolder
from app.services.acquisition_service import AcquisitionService
from app.services.media_library_service import media_library_service
from app.services.profile_manager import profile_manager
from app.services.watch_folder_manager import WatchFolderManager, watcher_service
from app.services.watch_routing import WatchRoutingService


@pytest.fixture
def setup_plan(monkeypatch, tmp_path):
    """仅使用临时路由和伪转换队列，不访问真实上传或配置。"""
    manager = WatchFolderManager()
    manager.watch_folders = {}
    routing = WatchRoutingService(tmp_path / 'routes.db')
    monkeypatch.setattr(import_module('app.services.watch_folder_manager'), 'watch_routing', routing)
    monkeypatch.setattr(import_module('app.services.watch_folder_manager'), 'watch_folder_manager', manager)
    monkeypatch.setattr(discovery, 'watch_folder_manager', manager)
    monkeypatch.setattr(watch_folders, 'watch_folder_manager', manager)
    monkeypatch.setattr(manager, 'save_watch_folders', lambda: None)
    monkeypatch.setattr(media_library_service, 'index_output', lambda _path: False)
    monkeypatch.setattr(tasks, 'tasks_cache', {})
    profiles = {
        'apple': Profile(id='apple', name='上传参数', output_format='m4a', codec='aac', apple_music_delivery_mode='direct_upload'),
        'plain': Profile(id='plain', name='普通转换', output_format='mp3'),
    }
    monkeypatch.setattr(profile_manager, 'get_profile', profiles.get)
    monkeypatch.setattr(metadata_service, 'read_metadata', lambda _path: {'title': '歌曲', 'artist': '歌手'})
    monkeypatch.setattr(discovery.dual_library_service, 'find_apple_candidates', lambda _track: [])
    incremental = []
    monkeypatch.setattr(discovery.dual_library_service, 'upsert_incremental_track', lambda *args: incremental.append(args))
    monkeypatch.setattr(discovery, 'invalidate_presence_index', lambda: None)
    queued = []

    async def enqueue(request, skip_existing=False):
        assert skip_existing
        queued.append(request)
        task = Task(id=str(len(queued)), source_file=request.source_file, output_file=request.output_file,
                    profile_id=request.profile_id, status='waiting', start_time=datetime.now())
        tasks.tasks_cache[task.id] = task
        return task

    monkeypatch.setattr(tasks, 'enqueue_conversion_task', enqueue)
    source = tmp_path / '歌曲.flac'
    source.write_bytes(b'original audio')
    folder = WatchFolder(id='plan', name='双库入库', default_target='both', targets=[
        DeliveryTarget(type='copy', output_dir=str(tmp_path / 'library')),
        DeliveryTarget(type='convert', profile_id='apple', output_dir=str(tmp_path / 'apple')),
        DeliveryTarget(type='convert', profile_id='plain', output_dir=str(tmp_path / 'mp3')),
    ])
    manager.watch_folders[folder.id] = folder
    return SimpleNamespace(manager=manager, routing=routing, source=source, folder=folder,
                           queued=queued, incremental=incremental)


def test_manual_only_plan_never_starts_monitoring(setup_plan, monkeypatch):
    """没有输入目录时不能监听当前目录，也不能触发初始或周期扫描。"""
    ctx = setup_plan
    watched = []
    monkeypatch.setattr(watcher_service, 'start_watch', lambda **kwargs: watched.append(kwargs))

    async def create():
        ctx.manager.loop = asyncio.get_running_loop()
        ctx.manager.create_watch_folder(ctx.folder)
        await asyncio.sleep(0)

    asyncio.run(create())
    assert not watched
    assert ctx.manager.get_status(ctx.folder.id)['watching'] is False
    assert ctx.manager.get_status(ctx.folder.id)['next_scan_at'] is None
    with pytest.raises(FileNotFoundError):
        ctx.manager.scan_watch_folder(ctx.folder.id)


def test_manual_conversion_reuses_all_outputs_and_survives_reload(setup_plan, tmp_path):
    """手动方案执行转换及复制，重载路由后不重复提交。"""
    ctx = setup_plan
    result = asyncio.run(ctx.manager.process_selected_file(ctx.folder, ctx.source))
    assert result['created_tasks'] == 2
    assert result['copied_files'] == 1
    assert (tmp_path / 'library' / ctx.source.name).read_bytes() == b'original audio'
    assert [request.profile_id for request in ctx.queued] == ['apple', 'plain']
    assert all(request.source_file == str(ctx.source) for request in ctx.queued)
    assert len(ctx.incremental) == 1
    repeated = asyncio.run(ctx.manager.process_selected_file(ctx.folder, ctx.source))
    assert repeated['created_tasks'] == repeated['copied_files'] == 0
    assert len(ctx.queued) == 2
    assert WatchRoutingService(tmp_path / 'routes.db').list_files('manual:plan:all')


@pytest.mark.parametrize('candidates', [[], [{'title': '歌曲'}], [{'title': '歌曲', 'verification_status': 'pending'}]])
def test_local_fill_only_uploads_local_source_without_downloading(setup_plan, monkeypatch, tmp_path, candidates):
    """疑似已有仅作提醒，本地补齐仍只执行 Apple 输出且不重新下载。"""
    ctx = setup_plan
    monkeypatch.setattr(media_library_service, 'load_tracks', lambda _refresh: [
        {'id': 'local', 'path': str(ctx.source), 'title': '歌曲', 'artist': '歌手'},
    ])
    monkeypatch.setattr(discovery.musicdl_client, 'start_download', lambda *_args: pytest.fail('不得重新下载'))
    monkeypatch.setattr(discovery.dual_library_service, 'find_apple_candidates', lambda _track: candidates)
    result = asyncio.run(discovery.fill_local_apple(discovery.LocalAppleFillRequest(
        local_file_id='local', processing_plan_id=ctx.folder.id)))
    assert result['created_tasks'] == 1
    assert result['copied_files'] == 0
    assert [request.profile_id for request in ctx.queued] == ['apple']
    assert ctx.queued[0].source_file == str(ctx.source)
    assert not (tmp_path / 'library').exists()
    assert len(ctx.incremental) == 1
    repeated = asyncio.run(discovery.fill_local_apple(discovery.LocalAppleFillRequest(
        local_file_id='local', processing_plan_id=ctx.folder.id)))
    assert repeated['created_tasks'] == 0
    assert len(ctx.queued) == 1


def test_local_fill_rejects_missing_source(setup_plan, monkeypatch):
    """本地文件失效仍停止处理，不隐式下载或上传。"""
    ctx = setup_plan
    ctx.source.unlink()
    monkeypatch.setattr(media_library_service, 'load_tracks', lambda _refresh: [{'id': 'local', 'path': str(ctx.source)}])
    with pytest.raises(HTTPException) as error:
        asyncio.run(discovery.fill_local_apple(discovery.LocalAppleFillRequest(local_file_id='local', processing_plan_id='plan')))
    assert error.value.status_code == 404
    assert not ctx.queued


def test_local_fill_rejects_plan_without_upload_rules(setup_plan):
    """普通转换参数不能被误当作 Apple Music 补齐规则。"""
    ctx = setup_plan
    folder = ctx.folder.model_copy(update={'targets': [ctx.folder.targets[0], ctx.folder.targets[2]]})
    with pytest.raises(ValueError, match='Apple Music'):
        asyncio.run(ctx.manager.process_selected_file(folder, ctx.source, apple_only=True))
    assert not ctx.queued


def test_selected_plan_never_overwrites_existing_output(setup_plan, tmp_path):
    """已有不同内容的同名文件应保留，并返回可见的冲突状态。"""
    ctx = setup_plan
    output = tmp_path / 'library' / ctx.source.name
    output.parent.mkdir()
    output.write_bytes(b'existing song')
    result = asyncio.run(ctx.manager.process_selected_file(ctx.folder, ctx.source))
    assert result['outputs'][0]['state'] == 'blocked'
    assert output.read_bytes() == b'existing song'


def test_local_precheck_reports_source_availability(setup_plan, monkeypatch):
    """对账预检查显示真实可读状态，失效后不得启用本地补齐按钮。"""
    ctx = setup_plan
    monkeypatch.setattr(media_library_service, 'load_tracks', lambda _refresh: [
        {'id': 'local', 'path': str(ctx.source), 'title': '歌曲'},
    ])
    monkeypatch.setattr(discovery.apple_catalog_service, 'search', lambda *_args: [])
    request = discovery.ApplePrecheckRequest(local_file_id='local')
    assert asyncio.run(discovery.precheck_apple_fill(request))['local_available'] is True
    ctx.source.unlink()
    assert asyncio.run(discovery.precheck_apple_fill(request))['local_available'] is False


def test_batch_plan_uses_saved_rules_instead_of_client_targets(setup_plan, monkeypatch, tmp_path):
    """操作台只传方案 ID，服务端使用已保存规则且不扫描输入目录。"""
    ctx = setup_plan
    monkeypatch.setattr(files, 'files_cache', {'file': {'path': str(ctx.source)}})
    result = asyncio.run(files.batch_deliver_files(files.FileBatchDeliveryRequest(
        file_ids=['file'], processing_plan_id='plan',
        targets=[DeliveryTarget(type='copy', output_dir=str(tmp_path / 'ignored'))])))
    assert not result['errors']
    assert len(result['deliveries']) == 3
    assert not (tmp_path / 'ignored').exists()


def test_api_can_create_and_clear_optional_input_directory(setup_plan, tmp_path):
    """方案允许省略监控目录；清空旧目录后仍保留输出规则。"""
    output = tmp_path / 'output'
    output.mkdir()
    created = asyncio.run(watch_folders.create_watch_folder(watch_folders.WatchFolderCreate(
        name='手动复制', targets=[DeliveryTarget(type='copy', output_dir=str(output))])))
    assert created.input_dir == ''
    folder = setup_plan.folder.model_copy(update={'input_dir': str(tmp_path), 'default_target': 'all'})
    setup_plan.manager.watch_folders[folder.id] = folder
    for target in folder.targets:
        Path(target.output_dir).mkdir(exist_ok=True)
    updated = asyncio.run(watch_folders.update_watch_folder(folder.id, watch_folders.WatchFolderUpdate(input_dir='')))
    assert updated.input_dir == ''
    assert updated.targets == folder.targets


def test_acquisition_missing_local_source_never_falls_back_to_download(monkeypatch, tmp_path):
    """旧补齐入口同样不能把失效的本地源静默改成重新下载。"""
    service = AcquisitionService(tmp_path / 'jobs.db')
    monkeypatch.setattr(service, 'start', lambda _id: None)
    monkeypatch.setattr(service, '_download', lambda *_args: pytest.fail('不得重新下载'))
    job = service.create_job(None, 'local', str(tmp_path / 'missing.flac'), False, True)
    service._run(job['id'])
    result = service.get_job(job['id'])
    assert result['status'] == 'failed'
    assert '本地源文件不可读取' in result['error']
