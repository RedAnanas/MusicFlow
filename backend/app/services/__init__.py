"""服务模块入口，按需加载以避免导入时产生配置写入等副作用。"""

from importlib import import_module


_SERVICE_EXPORTS = {
    "config_manager": ("app.services.config_manager", "config_manager"),
    "task_manager": ("app.services.task_manager", "task_manager"),
    "profile_manager": ("app.services.profile_manager", "profile_manager"),
    "watch_folder_manager": ("app.services.watch_folder_manager", "watch_folder_manager"),
    "apple_music_handoff_service": ("app.services.apple_music_handoff", "apple_music_handoff_service"),
}

__all__ = list(_SERVICE_EXPORTS)


def __getattr__(name):
    if name not in _SERVICE_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _SERVICE_EXPORTS[name]
    return getattr(import_module(module_name), attribute_name)
