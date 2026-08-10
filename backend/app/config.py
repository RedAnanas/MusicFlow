import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 基础路径
    MUSIC_SOURCE_DIR: str = "D:/Music"
    MUSIC_OUTPUT_DIR: str = "D:/Music/output"
    MUSIC_ARCHIVE_DIR: str = "D:/Music/archive"
    CONFIG_DIR: str = "D:/Documents/AI/MusicFlow/config"
    LOGS_DIR: str = "D:/Documents/AI/MusicFlow/logs"
    TEMP_DIR: str = "D:/Documents/AI/MusicFlow/temp"

    # FFmpeg 路径
    FFMPEG_PATH: str = "D:/download/ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"
    FFPROBE_PATH: str = "D:/download/ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


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
