"""读取仓库或镜像内唯一的应用版本来源。"""

from pathlib import Path


def get_app_version() -> str:
    """从向上查找的 VERSION 文件中读取版本号。"""
    for directory in Path(__file__).resolve().parents:
        version_file = directory / "VERSION"
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
    raise RuntimeError("未找到 VERSION 文件")


APP_VERSION = get_app_version()
