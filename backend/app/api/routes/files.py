import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from app.config import settings
from app.core import ffprobe_service, metadata_service
from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# 文件存储（内存缓存，实际应使用文件系统或JSON）
files_cache: dict = {}
file_list_cache: List[dict] = []
file_list_loaded = False


class FileResponse(BaseModel):
    id: str
    path: str
    filename: str
    format: str
    size: int
    duration: Optional[float] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    bitrate: Optional[int] = None
    channels: Optional[int] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    title: Optional[str] = None
    track: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None


class FileConvertRequest(BaseModel):
    profile_id: str
    output_dir: Optional[str] = None


class FileBatchConvertRequest(FileConvertRequest):
    file_ids: List[str]


class MetadataUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    albumartist: Optional[str] = None
    composer: Optional[str] = None
    genre: Optional[str] = None
    date: Optional[str] = None
    track: Optional[str] = None
    disc: Optional[str] = None
    comment: Optional[str] = None
    copyright: Optional[str] = None
    lyrics: Optional[str] = None


@router.get("/", response_model=List[FileResponse])
async def get_files(
    search: Optional[str] = Query(None, description="搜索关键词"),
    format: Optional[str] = Query(None, description="格式筛选"),
    refresh: bool = Query(False, description="强制重新扫描音乐目录"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制")
):
    """获取所有音乐文件"""
    global file_list_cache, file_list_loaded

    if refresh or not file_list_loaded:
        file_list_cache = _scan_files()
        file_list_loaded = True

    files = list(file_list_cache)

    # 应用搜索过滤
    if search:
        search_lower = search.lower()
        files = [
            file_data for file_data in files
            if any([
                search_lower in file_data["filename"].lower(),
                search_lower in (file_data["artist"] or "").lower(),
                search_lower in (file_data["album"] or "").lower(),
                search_lower in (file_data["title"] or "").lower(),
            ])
        ]

    # 应用格式过滤
    if format:
        files = [file_data for file_data in files if file_data["format"] == format.lower()]

    return files[:limit]


def _scan_files() -> List[dict]:
    """扫描源目录并读取音频信息，仅在首次加载或手动刷新时执行。"""
    files = []

    # 扫描所有配置的源目录
    source_dirs = [settings.MUSIC_SOURCE_DIR]

    for source_dir in source_dirs:
        dir_path = Path(source_dir)
        if not dir_path.exists():
            continue

        # 扫描音频文件
        for file_path in dir_path.rglob("*"):
            if not file_path.is_file():
                continue

            # 检查是否为支持的音频格式
            ext = file_path.suffix.lower()[1:]
            if ext not in settings.SUPPORTED_FORMATS:
                continue

            file_id = hashlib.md5(str(file_path).encode()).hexdigest()

            # 获取音频信息
            audio_info = ffprobe_service.get_audio_info(str(file_path))

            # 获取元数据
            metadata = metadata_service.read_metadata(str(file_path))

            file_data = {
                "id": file_id,
                "path": str(file_path),
                "filename": file_path.name,
                "format": ext,
                "size": file_path.stat().st_size,
                "duration": audio_info.get("duration") if audio_info else None,
                "sample_rate": audio_info.get("sample_rate") if audio_info else None,
                "bit_depth": audio_info.get("bits_per_sample") if audio_info else None,
                "bitrate": audio_info.get("bitrate") if audio_info else None,
                "channels": audio_info.get("channels") if audio_info else None,
                "artist": metadata.get("artist") if metadata else None,
                "album": metadata.get("album") if metadata else None,
                "title": metadata.get("title") if metadata else None,
                "track": metadata.get("track") if metadata else None,
                "year": metadata.get("date") if metadata else None,
                "genre": metadata.get("genre") if metadata else None,
            }

            files.append(file_data)

            # 缓存文件信息
            files_cache[file_id] = file_data

    return files


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    """获取单个文件信息"""
    if file_id in files_cache:
        return files_cache[file_id]

    raise HTTPException(status_code=404, detail="File not found")


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """删除音乐源目录内的文件。"""
    file_data = files_cache.get(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="文件不存在")

    source_root = Path(settings.MUSIC_SOURCE_DIR).resolve()
    file_path = Path(file_data["path"]).resolve()
    try:
        file_path.relative_to(source_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="禁止删除音乐源目录之外的文件") from exc

    if not file_path.is_file():
        files_cache.pop(file_id, None)
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        file_path.unlink()
    except OSError as exc:
        logger.error(f"Failed to delete file {file_path}: {exc}")
        raise HTTPException(status_code=500, detail=f"文件删除失败：{exc}") from exc

    files_cache.pop(file_id, None)
    global file_list_cache
    file_list_cache = [file_data for file_data in file_list_cache if file_data["id"] != file_id]
    logger.info(f"Deleted music file: {file_path}")
    return {"status": "success", "deleted": file_id}


@router.get("/{file_id}/metadata")
async def get_file_metadata(file_id: str):
    """获取文件元数据"""
    if file_id not in files_cache:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = files_cache[file_id]
    metadata = metadata_service.read_metadata(file_data["path"])

    if metadata is None:
        raise HTTPException(status_code=404, detail="Cannot read metadata")

    return metadata


@router.put("/{file_id}/metadata")
async def update_file_metadata(file_id: str, metadata_update: MetadataUpdate):
    """更新文件元数据"""
    if file_id not in files_cache:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = files_cache[file_id]
    metadata = metadata_update.model_dump(exclude_unset=True)

    success = metadata_service.write_metadata(file_data["path"], metadata)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update metadata")

    return {"status": "success", "message": "Metadata updated"}


async def queue_file_conversion(file_id: str, request: FileConvertRequest):
    """按配置创建单个转换任务。"""
    if file_id not in files_cache:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = files_cache[file_id]
    source_path = Path(file_data["path"])
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    from app.api.routes.tasks import TaskCreate, enqueue_conversion_task
    from app.services.profile_manager import profile_manager

    profile = profile_manager.get_profile(request.profile_id)
    if not profile or not profile.enabled:
        raise HTTPException(status_code=400, detail="转换配置不可用")

    output_root = Path(request.output_dir or settings.MUSIC_OUTPUT_DIR)
    if not output_root.is_absolute():
        raise HTTPException(status_code=400, detail="输出路径必须为绝对路径")
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建输出目录：{exc}") from exc

    output_file = output_root / source_path.name
    output_file = output_file.with_suffix(f".{profile.output_format.value}")
    task = await enqueue_conversion_task(
        TaskCreate(
            source_file=str(source_path),
            output_file=str(output_file),
            profile_id=profile.id,
        ),
        skip_existing=True,
    )
    if task is None:
        return {"status": "skipped", "output_file": str(output_file), "task_id": None}
    return {"status": "queued", "output_file": str(output_file), "task_id": task.id}


@router.post("/{file_id}/convert")
async def convert_file(file_id: str, request: FileConvertRequest):
    """转换单个文件。"""
    result = await queue_file_conversion(file_id, request)
    return {"status": "success", "converted": [result]}

@router.post("/batch-convert")
async def batch_convert_files(request: FileBatchConvertRequest):
    """批量创建转换任务。"""
    converted_files = []
    errors = []

    for file_id in request.file_ids:
        try:
            result = await queue_file_conversion(file_id, request)
            converted_files.append({"file_id": file_id, **result})
        except HTTPException as exc:
            errors.append({"file_id": file_id, "error": exc.detail})

    return {
        "status": "success",
        "message": f"已创建 {sum(item['status'] == 'queued' for item in converted_files)} 个转换任务",
        "converted": converted_files,
        "errors": errors
    }
