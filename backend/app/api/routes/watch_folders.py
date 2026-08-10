import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models import WatchFolder
from app.services.watch_folder_manager import watch_folder_manager

router = APIRouter()
logger = logging.getLogger(__name__)


class WatchFolderCreate(BaseModel):
    name: str
    input_dir: str
    profile_ids: List[str]
    auto_process: bool = True
    recursive_scan: bool = True
    scan_interval_minutes: int = 5
    output_dir: Optional[str] = None


class WatchFolderUpdate(BaseModel):
    name: Optional[str] = None
    input_dir: Optional[str] = None
    profile_ids: Optional[List[str]] = None
    auto_process: Optional[bool] = None
    recursive_scan: Optional[bool] = None
    scan_interval_minutes: Optional[int] = None
    output_dir: Optional[str] = None


class WatchFolderResponse(WatchFolderCreate):
    id: str
    enabled: bool = True
    watching: bool = False
    last_scan: Optional[str] = None
    last_scan_count: int = 0
    last_event: Optional[str] = None
    last_error: Optional[str] = None
    next_scan_at: Optional[str] = None
    created_tasks: int = 0


def validate_input_directory(directory: str):
    input_path = Path(directory)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {directory}")
    if not input_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")


def prepare_output_directory(directory: Optional[str]):
    if not directory:
        return
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create output directory {directory}: {exc}",
        ) from exc


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
    prepare_output_directory(folder_create.output_dir)

    folder = WatchFolder(
        id=str(uuid.uuid4()),
        **folder_create.model_dump(),
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
    if "output_dir" in update_data:
        prepare_output_directory(update_data["output_dir"])

    folder_data = existing_folder.model_dump()
    folder_data.update(update_data)
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
