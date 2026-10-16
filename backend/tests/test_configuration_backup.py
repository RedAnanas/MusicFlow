"""配置备份的往返、迁移与失败恢复回归。"""
import asyncio
import json
from unittest.mock import Mock

import pytest

from app.services import configuration_backup as backup
from app.services.config_manager import config_manager
from app.models import Profile, WatchFolder


@pytest.fixture
def environment(monkeypatch, tmp_path):
    from app.services.profile_manager import profile_manager
    from app.services.watch_folder_manager import watch_folder_manager
    from app.services.musicdl_client import musicdl_client
    from app.services.media_library_service import media_library_service
    from app.services.dual_library_config import dual_library_config
    from app.api.routes import files, library, discovery
    monkeypatch.setattr(config_manager, 'config_dir', tmp_path)
    for name, value in backup.GeneralSettings().model_dump().items():
        monkeypatch.setattr(backup.settings, name.upper(), value)
    profile = Profile(id='aac', name='中文方案', output_format='m4a', codec='aac')
    monkeypatch.setattr(profile_manager, 'profiles', {'aac': profile})
    monkeypatch.setattr(watch_folder_manager, 'watch_folders', {})
    monkeypatch.setattr(watch_folder_manager, 'runtime_status', {})
    monkeypatch.setattr(watch_folder_manager, 'event_history', {})
    monkeypatch.setattr(watch_folder_manager, 'next_scan_at', {})
    monkeypatch.setattr(musicdl_client, 'base_url', 'http://musicdl:5000')
    monkeypatch.setattr(media_library_service, 'get_named_sources', lambda: [])
    monkeypatch.setattr(dual_library_config, 'resolve', lambda: {'nas_watch_folder_id': '', 'apple_watch_folder_id': '', 'apple_storefront': 'cn'})
    monkeypatch.setattr(files, '_schedule_file_refresh', Mock())
    monkeypatch.setattr(files, '_replace_file_cache', Mock())
    monkeypatch.setattr(media_library_service, 'invalidate', Mock())
    monkeypatch.setattr(library, 'invalidate_reconciliation_cache', Mock())
    monkeypatch.setattr(discovery, 'invalidate_presence_index', Mock())
    return tmp_path


def test_导出往返只包含配置且格式稳定(environment):
    (environment / 'task_history.json').write_text('{"token":"do-not-export"}')
    (environment / 'apple-upload').mkdir()
    (environment / 'apple-upload/store.key').write_bytes(b'secret-key')
    bundle = backup.export_bundle()
    content = bundle.model_dump_json().encode()
    assert '中文方案' in content.decode()
    assert b'do-not-export' not in content and b'secret-key' not in content
    assert set(backup.parse_bundle(content).configuration.model_fields) == {'general', 'profiles', 'watch_folders', 'library_sources', 'media_sources', 'dual_library', 'musicdl'}
    assert backup.revision() == backup.revision()


def test_跨平台路径只预览不会创建目录(environment):
    bundle = backup.export_bundle()
    path = str(environment / '尚未挂载')
    bundle.configuration.library_sources = [path, r'D:\音乐']
    before = list(environment.iterdir())
    value = backup.preview(bundle)
    assert {item['path'] for item in value['paths'] if not item['available']} == {path, r'D:\音乐'}
    assert list(environment.iterdir()) == before


@pytest.mark.parametrize('change', [
    lambda value: value.update(format_version=99),
    lambda value: value.update(application='OtherApp'),
    lambda value: value['configuration'].update(authorization={'token':'private'}),
    lambda value: value['configuration']['musicdl'].update(base_url='http://user:private@host'),
    lambda value: value['configuration']['general'].update(max_concurrent_tasks=0),
    lambda value: value['configuration']['profiles']['aac'].update(id='other'),
    lambda value: value['configuration']['dual_library'].update(nas_watch_folder_id='missing'),
])
def test_非法配置或秘密字段在写入前拒绝(environment, change):
    value = backup.export_bundle().model_dump(mode='json')
    change(value)
    with pytest.raises(ValueError):
        backup.parse_bundle(json.dumps(value).encode())
    assert not list(environment.iterdir())


def test_拒绝过大损坏和非UTF8文件():
    for content in (b'x' * (backup.MAX_BYTES + 1), b'not json', b'\xff\xfe'):
        with pytest.raises(ValueError):
            backup.parse_bundle(content)


def test_方案引用完整性校验(environment):
    value = backup.export_bundle().model_dump(mode='json')
    value['configuration']['watch_folders'] = {'watch': {'id':'watch', 'name':'监控', 'input_dir':'/music', 'profile_ids':['missing']}}
    with pytest.raises(ValueError):
        backup.parse_bundle(json.dumps(value).encode())


def test_恢复保留方案ID并停用监控及生成旧备份(environment, monkeypatch):
    from app.services.profile_manager import profile_manager
    from app.services.watch_folder_manager import watch_folder_manager
    monkeypatch.setattr(backup, 'require_idle', lambda: None)
    bundle = backup.export_bundle()
    bundle.configuration.watch_folders['watch'] = WatchFolder(id='watch', name='监控', input_dir='/missing', profile_ids=['aac'])
    bundle.configuration.general.music_source_dir = '/new/music'
    original_revision = backup.revision()
    result = asyncio.run(backup.import_bundle(bundle, original_revision))
    assert profile_manager.profiles['aac'].name == '中文方案'
    assert watch_folder_manager.watch_folders['watch'].enabled is False
    assert json.loads((environment / 'watch_folders.json').read_text(encoding='utf-8'))['watch']['enabled'] is False
    old = backup.parse_bundle((environment / 'configuration-backups' / (result['backup_id']+'.json')).read_bytes())
    assert not old.configuration.watch_folders
    assert old.configuration.general.music_source_dir == ''
    assert backup.current_general().music_source_dir == '/new/music'
    backup.apply_general(backup.GeneralSettings())
    backup.load_general_settings()
    assert backup.current_general().music_source_dir == '/new/music'


def test_预览后配置变化拒绝覆盖(environment, monkeypatch):
    monkeypatch.setattr(backup, 'require_idle', lambda: None)
    bundle = backup.export_bundle()
    old = backup.revision()
    backup.apply_general(backup.GeneralSettings(music_source_dir='/changed'))
    with pytest.raises(ValueError, match='已变化'):
        asyncio.run(backup.import_bundle(bundle, old))
    assert not list(environment.iterdir())


def test_批量写入中途失败完整恢复文件(environment, monkeypatch):
    original = {'profiles.json': b'{"old":true}', 'settings.json': b'{"previous":true}'}
    for name, content in original.items():
        (environment / name).write_bytes(content)
    replace = backup.os.replace
    calls = 0
    def fail_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError('disk failure')
        return replace(source, target)
    monkeypatch.setattr(backup.os, 'replace', fail_once)
    with pytest.raises(OSError):
        backup.save_configuration(backup.export_bundle().configuration)
    for name, content in original.items():
        assert (environment / name).read_bytes() == content
    assert not (environment / 'watch_folders.json').exists()
    assert list((environment / 'configuration-backups').glob('*.json'))


def test_通用设置保存失败不修改内存(environment, monkeypatch):
    from app.api.routes.settings import update_settings
    from fastapi import HTTPException
    monkeypatch.setattr(config_manager, 'save', lambda *args: False)
    with pytest.raises(HTTPException):
        asyncio.run(update_settings(backup.GeneralSettings(music_source_dir='/new')))
    assert backup.current_general().music_source_dir == ''


def test_监控启用时不能导入(environment, monkeypatch):
    from app.services.watch_folder_manager import watch_folder_manager
    watch_folder_manager.watch_folders['watch'] = WatchFolder(id='watch', name='监控', input_dir='/music')
    with pytest.raises(ValueError, match='停用'):
        backup.require_idle()


def test_空方案列表重启后不擅自生成默认方案(environment):
    from app.services.profile_manager import ProfileManager
    assert config_manager.save('profiles.json', {})
    assert ProfileManager().profiles == {}
