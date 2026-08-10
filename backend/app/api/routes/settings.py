from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class SettingsResponse(BaseModel):
    music_source_dir: str = "/music/source"
    music_output_dir: str = "/music/output"
    music_archive_dir: str = "/music/archive"
    max_concurrent_tasks: int = 2
    ffmpeg_threads: int = 2
    file_stable_seconds: int = 30


@router.get("/", response_model=SettingsResponse)
async def get_settings():
    """获取系统设置"""
    from app.config import settings
    return SettingsResponse(
        music_source_dir=settings.MUSIC_SOURCE_DIR,
        music_output_dir=settings.MUSIC_OUTPUT_DIR,
        music_archive_dir=settings.MUSIC_ARCHIVE_DIR,
        max_concurrent_tasks=settings.MAX_CONCURRENT_TASKS,
        ffmpeg_threads=settings.FFMPEG_THREADS,
        file_stable_seconds=settings.FILE_STABLE_SECONDS,
    )


@router.put("/")
async def update_settings(settings_update: SettingsResponse):
    """更新系统设置"""
    from app.config import settings
    settings.MUSIC_SOURCE_DIR = settings_update.music_source_dir
    settings.MUSIC_OUTPUT_DIR = settings_update.music_output_dir
    settings.MUSIC_ARCHIVE_DIR = settings_update.music_archive_dir
    settings.MAX_CONCURRENT_TASKS = settings_update.max_concurrent_tasks
    settings.FFMPEG_THREADS = settings_update.ffmpeg_threads
    settings.FILE_STABLE_SECONDS = settings_update.file_stable_seconds
    return {"status": "success", "message": "Settings updated"}
