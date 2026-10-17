"""备份可迁移的用户配置，不包含授权、任务和数据库。"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import tempfile
from typing import Literal
from urllib.parse import urlsplit
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.models import Profile, WatchFolder
from app.services.config_manager import config_manager
from app.version import APP_VERSION

MAX_BYTES = 1024 * 1024
GENERAL_FILE = 'settings.json'


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    music_source_dir: str = ''
    music_output_dir: str = ''
    music_archive_dir: str = ''
    max_concurrent_tasks: int = Field(default=2, ge=1, le=32)
    ffmpeg_threads: int = Field(default=2, ge=1, le=128)
    file_stable_seconds: int = Field(default=30, ge=0, le=86400)


def current_general():
    return GeneralSettings(**{name: getattr(settings, name.upper()) for name in GeneralSettings.model_fields})


def apply_general(value):
    for name, item in value.model_dump().items():
        setattr(settings, name.upper(), item)


def load_general_settings():
    value = config_manager.load(GENERAL_FILE)
    if value is not None:
        try:
            apply_general(GeneralSettings.model_validate(value))
        except ValueError:
            logging.getLogger(__name__).warning('通用设置格式无效，使用当前环境默认值')


class MediaSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)


class DualLibrarySettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nas_watch_folder_id: str = ''
    apple_watch_folder_id: str = ''
    apple_storefront: str = 'cn'
    unified_watch_folder_id: str = ''


class MusicdlSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_url: str

    @model_validator(mode='after')
    def check_url(self):
        parsed = urlsplit(self.base_url)
        try:
            port = parsed.port
        except ValueError:
            raise ValueError('musicdl 地址端口无效') from None
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or self.base_url != f'{parsed.scheme}://{parsed.netloc}' or port == 0):
            raise ValueError('musicdl 地址必须是不含凭据、路径和参数的 HTTP 根地址')
        return self


class Configuration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    general: GeneralSettings
    profiles: dict[str, Profile]
    watch_folders: dict[str, WatchFolder]
    library_sources: list[str]
    media_sources: list[MediaSource]
    dual_library: DualLibrarySettings
    musicdl: MusicdlSettings

    @model_validator(mode='after')
    def check_references(self):
        for key, profile in self.profiles.items():
            if not key or profile.id != key:
                raise ValueError('转换方案 ID 不一致')
        for key, folder in self.watch_folders.items():
            if not key or folder.id != key:
                raise ValueError('监控目录 ID 不一致')
            references = folder.profile_ids + [target.profile_id for target in folder.targets if target.profile_id]
            if any(value not in self.profiles for value in references):
                raise ValueError('监控目录引用了不存在的转换方案')
        for value in (self.dual_library.nas_watch_folder_id, self.dual_library.apple_watch_folder_id, self.dual_library.unified_watch_folder_id):
            if value and value not in self.watch_folders:
                raise ValueError('双库配置引用了不存在的监控目录')
        return self


class ConfigurationBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    application: Literal['MusicFlow'] = 'MusicFlow'
    format_version: Literal[1] = 1
    app_version: str
    exported_at: str
    platform: str
    configuration: Configuration


def export_bundle():
    from app.services.profile_manager import profile_manager
    from app.services.watch_folder_manager import watch_folder_manager
    from app.services.media_library_service import media_library_service
    from app.services.dual_library_config import dual_library_config
    from app.services.musicdl_client import musicdl_client
    return ConfigurationBundle(app_version=APP_VERSION, exported_at=datetime.now(timezone.utc).isoformat(), platform=platform.system(),
        configuration=Configuration(general=current_general(), profiles=profile_manager.profiles,
            watch_folders=watch_folder_manager.watch_folders,
            library_sources=(config_manager.load('library_sources.json') or {}).get('paths', []),
            media_sources=media_library_service.get_named_sources(), dual_library=dual_library_config.resolve(),
            musicdl=MusicdlSettings(base_url=musicdl_client.base_url.rstrip('/'))))


def revision():
    content = json.dumps(export_bundle().configuration.model_dump(mode='json'), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def parse_bundle(content):
    if len(content) > MAX_BYTES:
        raise ValueError('配置文件不能超过 1 MiB')
    try:
        return ConfigurationBundle.model_validate(json.loads(content.decode('utf-8-sig')))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('配置包格式无效、版本不支持或配置引用不完整，请选择 MusicFlow 导出的 JSON 文件') from None


def preview(bundle):
    config = bundle.configuration
    paths = set(config.library_sources + [source.path for source in config.media_sources])
    paths.update(value for name, value in config.general.model_dump().items() if name.endswith('_dir') and value)
    for profile in config.profiles.values():
        paths.update(value for value in (profile.output_dir, profile.apple_music_import_dir) if value)
    for folder in config.watch_folders.values():
        paths.update(value for value in (folder.input_dir, folder.output_dir) if value)
        paths.update(target.output_dir for target in folder.targets)
    return {'app_version': bundle.app_version, 'platform': bundle.platform, 'current_revision': revision(),
            'counts': {'转换方案': len(config.profiles), '监控目录': len(config.watch_folders),
                       '音乐来源': len(config.library_sources), '媒体库目录': len(config.media_sources)},
            'paths': [{'path': path, 'available': Path(path).is_dir()} for path in sorted(paths)]}


def configuration_files(config):
    folders = {key: folder.model_copy(update={'enabled': False}).model_dump(mode='json') for key, folder in config.watch_folders.items()}
    return {GENERAL_FILE: config.general.model_dump(), 'profiles.json': {key: value.model_dump(mode='json') for key, value in config.profiles.items()},
            'watch_folders.json': folders, 'library_sources.json': {'paths': config.library_sources},
            'media_library_sources.json': {'sources': [source.model_dump() for source in config.media_sources]},
            'dual_library.json': config.dual_library.model_dump(), 'musicdl_connection.json': config.musicdl.model_dump()}


def save_configuration(config):
    """先暂存全部文件；写入失败时用原文件回滚，旧配置包保留供恢复。"""
    directory = config_manager.config_dir
    directory.mkdir(parents=True, exist_ok=True)
    values = configuration_files(config)
    backup_id = uuid.uuid4().hex
    backup = export_bundle().model_dump(mode='json')
    if not config_manager.save(f'configuration-backups/{backup_id}.json', backup):
        raise OSError('无法备份原配置，未执行导入')
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        staging = Path(temporary)
        existed = {}
        for name, value in values.items():
            target = directory / name
            if target.is_symlink():
                raise ValueError('配置文件不能是符号链接')
            existed[name] = target.exists()
            if target.exists():
                (staging / ('old-' + name)).write_bytes(target.read_bytes())
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        changed = []
        try:
            for name in values:
                os.replace(staging / name, directory / name)
                changed.append(name)
        except OSError:
            failed = False
            for name in reversed(changed):
                try:
                    if existed[name]:
                        os.replace(staging / ('old-' + name), directory / name)
                    else:
                        (directory / name).unlink(missing_ok=True)
                except OSError:
                    failed = True
            if failed:
                raise OSError('配置写入及回滚未完成，请先停止服务并从 configuration-backups 恢复导入前备份') from None
            raise OSError('配置写入失败，已恢复原文件；导入前备份保留在 configuration-backups') from None
    return backup_id


def require_idle():
    from app.services.conversion_engine import conversion_engine
    from app.services.watch_folder_manager import watch_folder_manager
    from app.services.acquisition_service import acquisition_service
    from app.api.routes import files
    stats = conversion_engine.get_stats()
    if (stats['queue_size'] or stats['active_count'] or any(folder.enabled for folder in watch_folder_manager.watch_folders.values())
            or any(thread.is_alive() for thread in acquisition_service._threads.values())
            or any(job.get('status') in {'queued', 'running', 'scanning', 'processing'} for job in files.import_jobs.values())):
        raise ValueError('请先停用全部监控目录，并等待转换、下载及文件导入任务结束后再恢复配置')


async def import_bundle(bundle, expected_revision):
    from app.services.watch_folder_manager import watch_folder_manager
    from app.services.profile_manager import profile_manager
    from app.services.musicdl_client import musicdl_client
    require_idle()
    if expected_revision != revision():
        raise ValueError('当前配置已变化，请重新预览后确认导入')
    backup_id = save_configuration(bundle.configuration)
    config = bundle.configuration
    apply_general(config.general)
    profile_manager.profiles = dict(config.profiles)
    watch_folder_manager.watch_folders = {key: value.model_copy(update={'enabled': False}) for key, value in config.watch_folders.items()}
    watch_folder_manager.runtime_status.clear()
    watch_folder_manager.event_history.clear()
    watch_folder_manager.next_scan_at.clear()
    musicdl_client.base_url = config.musicdl.base_url
    # 只刷新派生索引，不恢复任务或触发监控扫描。
    from app.api.routes import files, library, discovery
    from app.services.media_library_service import media_library_service
    files._replace_file_cache([])
    files._schedule_file_refresh()
    media_library_service.invalidate()
    library.invalidate_reconciliation_cache()
    discovery.invalidate_presence_index()
    return {'backup_id': backup_id, 'message': '配置已恢复；导入的监控已停用，请核对路径后启用。并发参数重启后生效。'}
