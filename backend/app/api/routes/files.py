import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from app.core import ffprobe_service, metadata_service
from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# 文件存储（内存缓存，实际应使用文件系统或JSON）
files_cache: dict = {}


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
    status: str = 'pending'


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
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制")
):
    """获取所有音乐文件"""
    from app.config import settings

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
                "status": "pending",
            }

            # 应用搜索过滤
            if search:
                search_lower = search.lower()
                if not any([
                    search_lower in file_data["filename"].lower(),
                    search_lower in (file_data["artist"] or "").lower(),
                    search_lower in (file_data["album"] or "").lower(),
                    search_lower in (file_data["title"] or "").lower(),
                ]):
                    continue

            # 应用格式过滤
            if format and file_data["format"] != format.lower():
                continue

            # 应用状态过滤
            if status and file_data["status"] != status:
                continue

            files.append(file_data)

            # 缓存文件信息
            files_cache[file_id] = file_data

    # 限制返回数量
    return files[:limit]


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    """获取单个文件信息"""
    if file_id in files_cache:
        return files_cache[file_id]

    raise HTTPException(status_code=404, detail="File not found")


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


@router.post("/{file_id}/convert")
async def convert_file(file_id: str, profile_ids: List[str]):
    """转换单个文件"""
    if file_id not in files_cache:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = files_cache[file_id]

    # TODO: 实现实际的转换逻辑
    logger.info(f"Converting file {file_data['filename']} with profiles {profile_ids}")

    return {
        "status": "success",
        "message": f"Conversion started for {file_data['filename']}",
        "task_ids": ["task-placeholder"]
    }


@router.post("/batch-convert")
async def batch_convert_files(file_ids: List[str], profile_ids: List[str]):
    """批量转换文件"""
    converted_files = []
    errors = []

    for file_id in file_ids:
        if file_id not in files_cache:
            errors.append({"file_id": file_id, "error": "File not found"})
            continue

        file_data = files_cache[file_id]
        converted_files.append({
            "file_id": file_id,
            "filename": file_data["filename"],
            "status": "queued"
        })

    # TODO: 实现实际的批量转换逻辑
    logger.info(f"Batch converting {len(converted_files)} files with profiles {profile_ids}")

    return {
        "status": "success",
        "message": f"Batch conversion started for {len(converted_files)} files",
        "converted": converted_files,
        "errors": errors
    }

