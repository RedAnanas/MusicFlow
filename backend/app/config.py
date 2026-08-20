from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # 基础路径
    MUSIC_SOURCE_DIR: str = "/mnt/d/Music/source"
    MUSIC_OUTPUT_DIR: str = "/mnt/d/Music/output"
    MUSIC_ARCHIVE_DIR: str = "/mnt/d/Music/archive"
    CONFIG_DIR: str = str(PROJECT_ROOT / "config")
    LOGS_DIR: str = str(PROJECT_ROOT / "logs")
    TEMP_DIR: str = str(PROJECT_ROOT / "temp")

    # FFmpeg 路径
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8082
    DEBUG: bool = False

    # 任务配置
    MAX_CONCURRENT_TASKS: int = 2
    FFMPEG_THREADS: int = 2
    FILE_STABLE_SECONDS: int = 30

    # 支持的音频格式
    SUPPORTED_FORMATS: List[str] = ["mp3", "flac", "m4a", "aac", "alac", "wav", "ape", "ogg", "opus", "wma"]

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def ensure_directories():
    """确保所有必需的目录存在"""
    directories = [
        settings.MUSIC_SOURCE_DIR,
        settings.MUSIC_OUTPUT_DIR,
        settings.MUSIC_ARCHIVE_DIR,
        settings.CONFIG_DIR,
        settings.LOGS_DIR,
        settings.TEMP_DIR,
    ]

    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
