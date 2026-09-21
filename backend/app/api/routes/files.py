import asyncio
import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from typing import List, Optional
from app.config import settings
from app.core import ffprobe_service, metadata_service
from app.models import DeliveryTarget, DeliveryTargetType
from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# 文件存储（内存缓存，实际应使用文件系统或JSON）
files_cache: dict = {}
file_list_cache: List[dict] = []
file_list_loaded = False
file_scan_lock = asyncio.Lock()


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


class FileBatchDeliveryRequest(BaseModel):
    file_ids: List[str]
    targets: List[DeliveryTarget]


class FileImportRequest(BaseModel):
    paths: List[str]


class LibrarySourceResponse(BaseModel):
    id: str
    path: str
    is_directory: bool
    exists: bool


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
        async with file_scan_lock:
            if refresh or not file_list_loaded:
                file_list_cache = await asyncio.to_thread(_scan_files)
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
    seen_ids = set()

    source_dirs = _load_library_sources()

    for source_dir in source_dirs:
        for file_path in _iter_audio_files(Path(source_dir)):
            file_data = _read_file(file_path)
            if file_data and file_data["id"] not in seen_ids:
                files.append(file_data)
                seen_ids.add(file_data["id"])
                files_cache[file_data["id"]] = file_data

    return files


def _load_library_sources() -> List[str]:
    data = config_manager.load("library_sources.json") or {}
    return [str(path) for path in data.get("paths", [])]


def _save_library_sources(paths: List[str]):
    if not config_manager.save("library_sources.json", {"paths": paths}):
        raise HTTPException(status_code=500, detail="保存音乐库来源失败")


def _source_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()


@router.get("/sources", response_model=List[LibrarySourceResponse])
async def get_library_sources():
    """返回用户主动添加的音乐库来源。"""
    return [
        LibrarySourceResponse(
            id=_source_id(path),
            path=path,
            is_directory=Path(path).is_dir(),
            exists=Path(path).exists(),
        )
        for path in _load_library_sources()
    ]


@router.delete("/sources/{source_id}")
async def remove_library_source(source_id: str):
    """停止读取音乐库来源，不删除磁盘上的文件或目录。"""
    sources = _load_library_sources()
    removed = next((path for path in sources if _source_id(path) == source_id), None)
    if not removed:
        raise HTTPException(status_code=404, detail="音乐库来源不存在")

    async with file_scan_lock:
        await asyncio.to_thread(_save_library_sources, [path for path in sources if path != removed])
        global file_list_cache, file_list_loaded
        files_cache.clear()
        file_list_cache = await asyncio.to_thread(_scan_files)
        file_list_loaded = True
    return {"status": "success", "removed": removed, "deleted_from_disk": False}


def _iter_audio_files(path: Path):
    candidates = path.rglob("*") if path.is_dir() else [path]
    for file_path in candidates:
        try:
            if file_path.is_file() and file_path.suffix.lower()[1:] in settings.SUPPORTED_FORMATS:
                yield file_path
        except OSError:
            continue


def _read_file(file_path: Path) -> Optional[dict]:
    try:
        ext = file_path.suffix.lower()[1:]
        audio_info = ffprobe_service.get_audio_info(str(file_path))
        metadata = metadata_service.read_metadata(str(file_path))
        return {
            "id": hashlib.md5(str(file_path).encode()).hexdigest(),
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
    except (OSError, ValueError) as exc:
        logger.warning(f"Cannot read audio file {file_path}: {exc}")
        return None


@router.post("/import")
async def import_files(request: FileImportRequest):
    """将服务器上的文件或目录加入音乐库，不复制源文件。"""
    if not request.paths:
        raise HTTPException(status_code=400, detail="至少选择一个文件或目录")

    async with file_scan_lock:
        existing_sources, imported, errors = await asyncio.to_thread(
            _collect_imported_files,
            request.paths,
        )
        await asyncio.to_thread(_save_library_sources, existing_sources)
        global file_list_cache, file_list_loaded
        merged = {item["id"]: item for item in file_list_cache}
        merged.update({item["id"]: item for item in imported})
        file_list_cache = list(merged.values())
        files_cache.update({item["id"]: item for item in imported})
        file_list_loaded = True
    return {"imported": imported, "errors": errors}


def _collect_imported_files(raw_paths: List[str]):
    """在工作线程中扫描导入路径，避免大型音乐库阻塞 API 事件循环。"""
    existing_sources = _load_library_sources()
    imported = []
    errors = []
    for raw_path in raw_paths:
        path = Path(raw_path).expanduser()
        if not path.is_absolute() or not path.exists():
            errors.append({"path": raw_path, "error": "路径不存在或不是绝对路径"})
            continue
        if path.is_file() and path.suffix.lower()[1:] not in settings.SUPPORTED_FORMATS:
            errors.append({"path": raw_path, "error": "不支持的音频格式"})
            continue
        normalized = str(path)
        if normalized not in existing_sources:
            existing_sources.append(normalized)
        for file_path in _iter_audio_files(path):
            file_data = _read_file(file_path)
            if file_data:
                imported.append(file_data)
    return existing_sources, imported, errors


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    """获取单个文件信息"""
    if file_id in files_cache:
        return files_cache[file_id]

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/{file_id}/cover")
async def get_file_cover(file_id: str):
    """按需返回音频内嵌封面，避免文件列表携带大块二进制数据。"""
    file_data = files_cache.get(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")

    metadata = metadata_service.read_metadata(file_data["path"])
    cover = metadata.get("cover") if metadata else None
    if not cover or not cover.get("data"):
        raise HTTPException(status_code=404, detail="Cover not found")

    return Response(
        content=bytes(cover["data"]),
        media_type=cover.get("mime") or "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """删除音乐源目录内的文件。"""
    file_data = files_cache.get(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = Path(file_data["path"]).resolve()
    source_paths = [Path(path).resolve() for path in _load_library_sources()]
    if not any(
        file_path == source_path or (source_path.is_dir() and file_path.is_relative_to(source_path))
        for source_path in source_paths
    ):
        raise HTTPException(status_code=403, detail="禁止删除音乐库来源之外的文件")

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

    output_dir = request.output_dir or profile.output_dir
    if not output_dir:
        raise HTTPException(status_code=400, detail="请先选择输出目录")
    output_root = Path(output_dir)
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


async def queue_file_copy(file_id: str, target: DeliveryTarget):
    """按监控目录同样的安全规则原样复制单个文件。"""
    if file_id not in files_cache:
        raise HTTPException(status_code=404, detail="File not found")

    source_path = Path(files_cache[file_id]["path"])
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    output_root = Path(target.output_dir)
    if not output_root.is_absolute():
        raise HTTPException(status_code=400, detail="输出路径必须为绝对路径")
    output_file = output_root / source_path.name

    def copy_file() -> bool:
        if output_file.exists():
            return False
        output_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = output_file.with_name(f".{output_file.name}.{uuid.uuid4().hex}.part")
        try:
            shutil.copy2(source_path, temporary_file)
            if output_file.exists():
                return False
            temporary_file.replace(output_file)
            return True
        finally:
            if temporary_file.exists():
                temporary_file.unlink()

    copied = await asyncio.to_thread(copy_file)
    return {
        "status": "copied" if copied else "skipped",
        "output_file": str(output_file),
        "task_id": None,
    }


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


@router.post("/batch-deliver")
async def batch_deliver_files(request: FileBatchDeliveryRequest):
    """按监控目录输出规则对已选文件执行转换和原样复制。"""
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="至少选择一个文件")
    if not request.targets:
        raise HTTPException(status_code=400, detail="至少配置一条输出规则")

    deliveries = []
    errors = []
    for file_id in request.file_ids:
        for target in request.targets:
            try:
                if target.type == DeliveryTargetType.CONVERT:
                    if not target.profile_id:
                        raise HTTPException(status_code=400, detail="转换输出规则必须选择转换方案")
                    result = await queue_file_conversion(file_id, FileConvertRequest(
                        profile_id=target.profile_id,
                        output_dir=target.output_dir,
                    ))
                else:
                    result = await queue_file_copy(file_id, target)
                deliveries.append({"file_id": file_id, "type": target.type.value, **result})
            except HTTPException as exc:
                errors.append({"file_id": file_id, "type": target.type.value, "error": exc.detail})

    return {"status": "success", "deliveries": deliveries, "errors": errors}
