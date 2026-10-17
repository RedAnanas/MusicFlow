"""投递保留正常文件名，内容冲突和任务目标在内部安全关联。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock
import os
import shutil
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models import DeliveryTarget, WatchFolder
from app.services.acquisition_service import AcquisitionService
from app.services.watch_routing import WatchRoutingService


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    folder = WatchFolder(id='inbox', name='统一入口', input_dir=str(inbox), targets=[
        DeliveryTarget(type='copy', output_dir=str(tmp_path / 'local')),
        DeliveryTarget(type='convert', profile_id='aac', output_dir=str(tmp_path / 'apple')),
    ])
    database = tmp_path / 'state.db'
    service = AcquisitionService(database)
    service.initialize()
    service._update = Mock()
    routes = WatchRoutingService(database)
    monkeypatch.setattr('app.services.watch_routing.watch_routing', routes)
    monkeypatch.setattr('app.services.acquisition_service.watch_folder_manager.get_watch_folder', lambda _: folder)
    monkeypatch.setattr('app.services.acquisition_service.watch_folder_manager.loop', None)

    def source(directory, data=b'audio'):
        parent = tmp_path / directory
        parent.mkdir()
        path = parent / '心型圈 - 蔡依林.flac'
        path.write_bytes(data)
        return path

    return service, routes, folder, source


def test_首次投递不在歌名追加任务编号(delivery):
    service, routes, folder, source = delivery
    path = service._deliver_to_watch_folder(source('first'), 'job-123', folder.id, '统一', (True, False))
    assert path.name == '心型圈 - 蔡依林.flac'
    assert routes.get(folder.id, path)['job_ids'] == ['job-123']
    assert path.read_bytes() == b'audio'


def test_同名同内容复用文件并保留已提交任务(delivery):
    service, routes, folder, source = delivery
    path = service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (False, True))
    plan = routes.get(folder.id, path)
    plan['outputs'][0].update(state='submitted', task_id='original-upload')
    routes.save(folder.id, path, plan)
    before = path.stat()
    again = service._deliver_to_watch_folder(source('second'), 'job-2', folder.id, '统一', (True, True))
    assert path == again
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    saved = routes.get(folder.id, path)
    assert saved['job_ids'] == ['job-1', 'job-2']
    apple = next(item for item in saved['outputs'] if item['library'] == 'apple')
    assert apple['task_id'] == 'original-upload' and apple['state'] == 'submitted'
    assert next(item for item in saved['outputs'] if item['library'] == 'nas')['state'] == 'waiting'
    assert len(list(path.parent.glob('*.flac'))) == 1


def test_内容不同才增加编号且不覆盖已有冲突文件(delivery):
    service, _, folder, source = delivery
    paths = [service._deliver_to_watch_folder(source(str(i), bytes([i])), f'job-{i}', folder.id, '统一', (True, False)) for i in range(3)]
    assert [p.name for p in paths] == ['心型圈 - 蔡依林.flac', '心型圈 - 蔡依林 (2).flac', '心型圈 - 蔡依林 (3).flac']
    assert [p.read_bytes() for p in paths] == [b'\0', b'\1', b'\2']


def test_并发投递同名不同内容不互相覆盖(delivery):
    service, _, folder, source = delivery
    sources = [source(str(i), bytes([i])) for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda pair: service._deliver_to_watch_folder(pair[1], str(pair[0]), folder.id, '统一', (True, False)), enumerate(sources)))
    assert len(set(paths)) == 4
    assert [p.read_bytes() for p in paths] == [bytes([i]) for i in range(4)]


def test_处理旧快照时不会丢失后来追加的目标(delivery):
    service, routes, folder, source = delivery
    path = service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (True, False))
    old = routes.get(folder.id, path)
    service._deliver_to_watch_folder(source('second'), 'job-2', folder.id, '统一', (False, True))
    old['outputs'][0]['state'] = 'success'
    routes.save(folder.id, path, old)
    saved = routes.get(folder.id, path)
    assert {item['library']: item['state'] for item in saved['outputs']} == {'nas': 'success', 'apple': 'waiting'}
    assert saved['job_ids'] == ['job-1', 'job-2']


def test_并发发布冲突回滚路由且不污染先到文件(delivery, monkeypatch):
    service, routes, folder, source = delivery
    link = os.link
    calls = []

    def race(temporary, target):
        if not calls:
            calls.append(target)
            target.write_bytes(b'other')
            shutil.copystat(temporary, target)
            raise FileExistsError()
        link(temporary, target)

    monkeypatch.setattr('app.services.acquisition_service.os.link', race)
    path = service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (False, True))
    assert path.name == '心型圈 - 蔡依林 (2).flac'
    assert calls[0].read_bytes() == b'other'
    assert routes.get(folder.id, calls[0]) is None
    assert routes.get(folder.id, path)['job_ids'] == ['job-1']


def test_旧处理快照不会恢复用户已移除的目标(delivery):
    service, routes, folder, source = delivery
    path = service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (True, True))
    old = routes.get(folder.id, path)
    routes.register(folder, path, path, True, False, replace=True)
    routes.save(folder.id, path, old)
    saved = routes.get(folder.id, path)
    assert saved['apple'] is False
    assert [item['library'] for item in saved['outputs']] == ['nas']


def test_并发同内容只保留一份且关联两个目标(delivery):
    service, routes, folder, source = delivery
    sources = [source('first'), source('second')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda i: service._deliver_to_watch_folder(sources[i], f'job-{i}', folder.id, '统一', (i == 0, i == 1)), range(2)))
    assert paths[0] == paths[1]
    saved = routes.get(folder.id, paths[0])
    assert set(saved['job_ids']) == {'job-0', 'job-1'}
    assert {item['library'] for item in saved['outputs']} == {'nas', 'apple'}


def test_发布失败回滚路由并清理临时文件(delivery, monkeypatch):
    service, routes, folder, source = delivery
    monkeypatch.setattr('app.services.acquisition_service.os.link', Mock(side_effect=OSError('发布失败')))
    with pytest.raises(OSError):
        service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (False, True))
    assert list(Path(folder.input_dir).iterdir()) == []
    assert routes.list_files(folder.id) == []


def test_重试仅本地任务不重试共享文件的苹果任务(delivery, monkeypatch):
    from app.api.routes import tasks
    service, routes, folder, source = delivery
    path = service._deliver_to_watch_folder(source('first'), 'job-1', folder.id, '统一', (True, True))
    plan = routes.get(folder.id, path)
    apple = next(item for item in plan['outputs'] if item['library'] == 'apple')
    apple.update(state='failed', task_id='apple-task')
    task = tasks.TaskResponse(id='apple-task', source_file=str(path), output_file='test.m4a', profile_id='aac', status='failed')
    monkeypatch.setattr(tasks, 'tasks_cache', {task.id: task})
    retry = AsyncMock()
    monkeypatch.setattr(tasks, 'retry_task', retry)
    monkeypatch.setattr('app.services.acquisition_service.watch_folder_manager._process_file', AsyncMock())
    asyncio.run(service._retry_routed_outputs(folder.id, plan, {'nas'}))
    retry.assert_not_called()
