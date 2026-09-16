import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models import DeliveryTarget, DeliveryTargetType, WatchFolder
from app.services.watch_folder_manager import watch_folder_manager

router = APIRouter()
logger = logging.getLogger(__name__)


class WatchFolderCreate(BaseModel):
    name: str
    input_dir: str
    profile_ids: List[str] = []
    targets: List[DeliveryTarget] = []
    auto_process: bool = True
    recursive_scan: bool = True
    scan_interval_minutes: int = 5
    output_dir: Optional[str] = None


class WatchFolderUpdate(BaseModel):
    name: Optional[str] = None
    input_dir: Optional[str] = None
    profile_ids: Optional[List[str]] = None
    targets: Optional[List[DeliveryTarget]] = None
    auto_process: Optional[bool] = None
    recursive_scan: Optional[bool] = None
    scan_interval_minutes: Optional[int] = None
    output_dir: Optional[str] = None


class WatchFolderResponse(WatchFolderCreate):
    id: str
    output_dir: Optional[str] = None
    enabled: bool = True
    watching: bool = False
    last_scan: Optional[str] = None
    last_scan_count: int = 0
    last_event: Optional[str] = None
    last_error: Optional[str] = None
    next_scan_at: Optional[str] = None
    created_tasks: int = 0
    copied_files: int = 0


def validate_input_directory(directory: str):
    input_path = Path(directory)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {directory}")
    if not input_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")


def prepare_output_directory(directory: str, input_directory: str):
    path = Path(directory)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {directory}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")
    try:
        path.resolve().relative_to(Path(input_directory).resolve())
    except ValueError:
        return
    raise HTTPException(status_code=400, detail="输出目录不能位于监控目录内，以免重复处理文件")


def normalize_targets(folder_data: Dict[str, Any]) -> List[DeliveryTarget]:
    targets = folder_data.get("targets") or []
    if targets:
        return [
            target
            if isinstance(target, DeliveryTarget)
            else DeliveryTarget.model_validate(target)
            for target in targets
        ]

    output_dir = folder_data.get("output_dir")
    profile_ids = folder_data.get("profile_ids") or []
    if output_dir and profile_ids:
        return [
            DeliveryTarget(
                type=DeliveryTargetType.CONVERT,
                profile_id=profile_id,
                output_dir=output_dir,
            )
            for profile_id in profile_ids
        ]
    return []


def validate_targets(targets: List[DeliveryTarget], input_directory: str):
    if not targets:
        raise HTTPException(status_code=400, detail="至少选择一个投递目标")
    for target in targets:
        if target.type == DeliveryTargetType.CONVERT and not target.profile_id:
            raise HTTPException(status_code=400, detail="转换输出规则必须选择转换方案")
        if target.type == DeliveryTargetType.COPY and target.profile_id:
            raise HTTPException(status_code=400, detail="原样复制规则不能关联转换方案")
        prepare_output_directory(target.output_dir, input_directory)


def build_response(folder: WatchFolder) -> WatchFolderResponse:
    data = folder.model_dump()
    data.update(watch_folder_manager.get_status(folder.id))
    return WatchFolderResponse(**data)


@router.get("/", response_model=List[WatchFolderResponse])
async def get_watch_folders():
    return [build_response(folder) for folder in watch_folder_manager.get_all_watch_folders()]


@router.get("/{folder_id}", response_model=WatchFolderResponse)
async def get_watch_folder(folder_id: str):
    folder = watch_folder_manager.get_watch_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Watch folder not found")
    return build_response(folder)


@router.post("/", response_model=WatchFolderResponse)
async def create_watch_folder(folder_create: WatchFolderCreate):
    validate_input_directory(folder_create.input_dir)
    folder_data = folder_create.model_dump()
    folder_data["targets"] = normalize_targets(folder_data)
    validate_targets(folder_data["targets"], folder_create.input_dir)

    folder = WatchFolder(
        id=str(uuid.uuid4()),
        **folder_data,
        enabled=True,
    )
    watch_folder_manager.create_watch_folder(folder)
    return build_response(folder)


@router.put("/{folder_id}", response_model=WatchFolderResponse)
async def update_watch_folder(folder_id: str, folder_update: WatchFolderUpdate):
    existing_folder = watch_folder_manager.get_watch_folder(folder_id)
    if not existing_folder:
        raise HTTPException(status_code=404, detail="Watch folder not found")

    update_data = folder_update.model_dump(exclude_unset=True)
    if update_data.get("input_dir"):
        validate_input_directory(update_data["input_dir"])
    folder_data = existing_folder.model_dump()
    folder_data.update(update_data)
    folder_data["targets"] = normalize_targets(folder_data)
    validate_targets(folder_data["targets"], folder_data["input_dir"])
    updated_folder = WatchFolder(**folder_data)
    watch_folder_manager.update_watch_folder(folder_id, updated_folder)
    return build_response(updated_folder)


@router.delete("/{folder_id}")
async def delete_watch_folder(folder_id: str):
    if not watch_folder_manager.delete_watch_folder(folder_id):
        raise HTTPException(status_code=404, detail="Watch folder not found")
    return {"status": "success", "message": f"Watch folder {folder_id} deleted"}


@router.post("/{folder_id}/scan")
async def scan_watch_folder(folder_id: str):
    if not watch_folder_manager.get_watch_folder(folder_id):
        raise HTTPException(status_code=404, detail="Watch folder not found")
    try:
        files = watch_folder_manager.scan_watch_folder(folder_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = watch_folder_manager.get_status(folder_id)
    return {
        "status": "success",
        "message": f"Found {len(files)} audio files",
        "files": files,
        "last_scan": status.get("last_scan"),
    }


@router.post("/{folder_id}/process")
async def process_watch_folder(folder_id: str):
    if not watch_folder_manager.get_watch_folder(folder_id):
        raise HTTPException(status_code=404, detail="Watch folder not found")
    try:
        result = await watch_folder_manager.process_watch_folder(folder_id, "manual")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", **result}


@router.get("/{folder_id}/status")
async def get_watch_folder_status(folder_id: str):
    if not watch_folder_manager.get_watch_folder(folder_id):
        raise HTTPException(status_code=404, detail="Watch folder not found")
    return watch_folder_manager.get_status(folder_id)


@router.get("/{folder_id}/events", response_model=List[Dict[str, Any]])
async def get_watch_folder_events(
    folder_id: str,
    limit: int = Query(50, ge=1, le=100),
):
    if not watch_folder_manager.get_watch_folder(folder_id):
        raise HTTPException(status_code=404, detail="Watch folder not found")
    return watch_folder_manager.get_events(folder_id, limit)


@router.post("/{folder_id}/toggle", response_model=WatchFolderResponse)
async def toggle_watch_folder(folder_id: str):
    folder = watch_folder_manager.toggle_watch_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Watch folder not found")
    return build_response(folder)
