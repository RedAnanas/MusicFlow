import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# 监控目录存储（内存缓存）
watch_folders_cache: dict = {}


class WatchFolderCreate(BaseModel):
    name: str
    input_dir: str
    profile_ids: List[str]
    auto_process: bool = True
    recursive_scan: bool = True
    scan_interval_minutes: int = 5


class WatchFolderUpdate(BaseModel):
    """监控目录更新模型 - 所有字段可选"""
    name: str = None
    input_dir: str = None
    profile_ids: List[str] = None
    auto_process: bool = None
    recursive_scan: bool = None
    scan_interval_minutes: int = None


class WatchFolderResponse(WatchFolderCreate):
    id: str
    enabled: bool = True
    last_scan: Optional[str] = None


@router.get("/", response_model=List[WatchFolderResponse])
async def get_watch_folders():
    """获取所有监控目录"""
    return list(watch_folders_cache.values())


@router.get("/{folder_id}", response_model=WatchFolderResponse)
async def get_watch_folder(folder_id: str):
    """获取单个监控目录"""
    if folder_id not in watch_folders_cache:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    return watch_folders_cache[folder_id]


@router.post("/", response_model=WatchFolderResponse)
async def create_watch_folder(folder_create: WatchFolderCreate):
    """创建监控目录"""
    # 验证目录是否存在
    input_path = Path(folder_create.input_dir)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {folder_create.input_dir}")

    if not input_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {folder_create.input_dir}")

    folder_id = str(uuid.uuid4())

    folder = WatchFolderResponse(
        id=folder_id,
        name=folder_create.name,
        input_dir=folder_create.input_dir,
        profile_ids=folder_create.profile_ids,
        auto_process=folder_create.auto_process,
        recursive_scan=folder_create.recursive_scan,
        scan_interval_minutes=folder_create.scan_interval_minutes,
        enabled=True,
        last_scan=None,
    )

    watch_folders_cache[folder_id] = folder
    logger.info(f"Created watch folder: {folder.name} ({folder.input_dir})")

    return folder


@router.put("/{folder_id}", response_model=WatchFolderResponse)
async def update_watch_folder(folder_id: str, folder_update: dict):
    """更新监控目录 - 支持部分更新"""
    if folder_id not in watch_folders_cache:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    existing_folder = watch_folders_cache[folder_id]

    # 合并更新数据
    update_data = {k: v for k, v in folder_update.items() if v is not None}

    # 如果更新了输入目录，验证目录是否存在
    if 'input_dir' in update_data:
        input_path = Path(update_data['input_dir'])
        if not input_path.exists():
            raise HTTPException(status_code=400, detail=f"Directory does not exist: {update_data['input_dir']}")
        if not input_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {update_data['input_dir']}")

    # 构建更新后的监控目录
    folder_dict = existing_folder.dict()
    folder_dict.update(update_data)

    updated_folder = WatchFolderResponse(**folder_dict)

    watch_folders_cache[folder_id] = updated_folder
    logger.info(f"Updated watch folder: {folder_id}")

    return updated_folder


@router.delete("/{folder_id}")
async def delete_watch_folder(folder_id: str):
    """删除监控目录"""
    if folder_id not in watch_folders_cache:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    folder = watch_folders_cache.pop(folder_id)
    logger.info(f"Deleted watch folder: {folder.name}")

    return {"status": "success", "message": f"Watch folder {folder_id} deleted"}


@router.post("/{folder_id}/scan")
async def scan_watch_folder(folder_id: str):
    """立即扫描监控目录"""
    if folder_id not in watch_folders_cache:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    folder = watch_folders_cache[folder_id]

    # 扫描目录
    input_path = Path(folder.input_dir)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail="Directory does not exist")

    # 查找音频文件
    audio_files = []
    pattern = "**/*" if folder.recursive_scan else "*"

    for file_path in input_path.glob(pattern):
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()[1:]
        if ext in settings.SUPPORTED_FORMATS:
            audio_files.append(str(file_path))

    # 更新最后扫描时间
    folder.last_scan = datetime.now().isoformat()

    logger.info(f"Scanned {folder.name}: found {len(audio_files)} audio files")

    return {
        "status": "success",
        "message": f"Found {len(audio_files)} audio files",
        "files": audio_files,
        "last_scan": folder.last_scan,
    }


@router.post("/{folder_id}/toggle")
async def toggle_watch_folder(folder_id: str):
    """启用/禁用监控目录"""
    if folder_id not in watch_folders_cache:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    folder = watch_folders_cache[folder_id]
    folder.enabled = not folder.enabled

    logger.info(f"Toggle watch folder {folder_id}: {'enabled' if folder.enabled else 'disabled'}")

    return {
        "status": "success",
        "message": f"Watch folder {'enabled' if folder.enabled else 'disabled'}",
        "enabled": folder.enabled,
    }

