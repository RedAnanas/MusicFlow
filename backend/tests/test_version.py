from pathlib import Path

from app.version import APP_VERSION


def test_app_version_uses_root_version_file():
    """后端运行时版本必须与唯一版本来源一致。"""
    version_file = Path(__file__).resolve().parents[2] / "VERSION"

    assert APP_VERSION == version_file.read_text(encoding="utf-8").strip()
