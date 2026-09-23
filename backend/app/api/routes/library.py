import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.services.dual_library_service import dual_library_service
from app.services.acquisition_service import acquisition_service
from app.services.media_library_service import media_library_service


router = APIRouter()
reconciliation_cache: Optional[dict] = None


class MatchDecisionRequest(BaseModel):
    local_file_id: str
    apple_track_key: str
    decision: Literal["confirmed", "rejected"]


class BatchMatchDecisionRequest(BaseModel):
    matches: list[MatchDecisionRequest]


class MediaLibrarySourceRequest(BaseModel):
    name: str
    path: str


class AppleIncrementalTrackRequest(BaseModel):
    apple_id: str = ""
    title: str
    artist: str
    album: str = ""
    isrc: str = ""
    source: Literal["manual", "catalog"] = "manual"


def invalidate_reconciliation_cache() -> None:
    global reconciliation_cache
    reconciliation_cache = None
    dual_library_service.clear_reconciliation_cache()


def invalidate_presence_index() -> None:
    from app.api.routes import discovery

    discovery.invalidate_presence_index()


@router.get("/library/media-sources")
async def get_media_library_sources():
    """返回资料库对账专用的整理后媒体库目录。"""
    return [
        {
            "id": media_library_service.source_id(source["path"]),
            **source,
            "exists": Path(source["path"]).exists(),
            "is_directory": Path(source["path"]).is_dir(),
        }
        for source in await asyncio.to_thread(media_library_service.get_named_sources)
    ]


@router.post("/library/media-sources")
async def add_media_library_sources(request: MediaLibrarySourceRequest):
    try:
        source = await asyncio.to_thread(media_library_service.add_source, request.name, request.path)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    return source


@router.put("/library/media-sources/{source_id}")
async def update_media_library_source(source_id: str, request: MediaLibrarySourceRequest):
    try:
        source = await asyncio.to_thread(media_library_service.update_source, source_id, request.name, request.path)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    return source


@router.delete("/library/media-sources/{source_id}")
async def remove_media_library_source(source_id: str):
    try:
        await asyncio.to_thread(media_library_service.remove_source, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    return {"status": "success"}


@router.post("/apple-library/snapshots")
async def import_apple_library_snapshot(file: UploadFile = File(...)):
    """导入 TuneMyMusic Apple Music CSV 快照。"""
    if await asyncio.to_thread(dual_library_service.get_latest_snapshot):
        raise HTTPException(status_code=409, detail="已有快照，请使用更新快照")
    return await _save_apple_library_snapshot(file)


@router.put("/apple-library/snapshots/{snapshot_id}")
async def update_apple_library_snapshot(snapshot_id: str, file: UploadFile = File(...)):
    """用新 CSV 原子更新当前快照。"""
    return await _save_apple_library_snapshot(file, snapshot_id)


async def _save_apple_library_snapshot(file: UploadFile, replace_snapshot_id: Optional[str] = None):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请选择 CSV 文件")
    content = await file.read(10 * 1024 * 1024 + 1)
    try:
        snapshot, created = await asyncio.to_thread(
            dual_library_service.import_snapshot,
            file.filename,
            content,
            replace_snapshot_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if created:
        await asyncio.to_thread(acquisition_service.confirm_apple_presence)
        invalidate_reconciliation_cache()
        invalidate_presence_index()
    return {"created": created, "snapshot": snapshot}


@router.delete("/apple-library/snapshots/{snapshot_id}")
async def delete_apple_library_snapshot(snapshot_id: str):
    """删除导入的 Apple Music CSV 快照，不影响本地音乐文件。"""
    try:
        await asyncio.to_thread(dual_library_service.delete_snapshot, snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    invalidate_presence_index()
    return {"status": "success"}


@router.get("/apple-library/entries")
async def list_apple_incremental_entries():
    """返回手动添加和自动交接产生的 Apple Music 增量记录。"""
    return await asyncio.to_thread(dual_library_service.list_incremental_tracks)


@router.post("/apple-library/entries")
async def add_apple_incremental_entry(request: AppleIncrementalTrackRequest):
    """记录已在 Apple Music 添加或准备交接的曲目，等待 CSV 快照确认。"""
    try:
        entry = await asyncio.to_thread(
            dual_library_service.upsert_incremental_track,
            request.model_dump(),
            request.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_presence_index()
    return entry


@router.delete("/apple-library/entries/{entry_id}")
async def delete_apple_incremental_entry(entry_id: str):
    try:
        await asyncio.to_thread(dual_library_service.delete_incremental_track, entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invalidate_presence_index()
    return {"status": "success"}


@router.post("/apple-library/entries/{entry_id}/confirm")
async def confirm_apple_incremental_entry(entry_id: str):
    try:
        entry = await asyncio.to_thread(dual_library_service.confirm_incremental_track, entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invalidate_presence_index()
    return entry


@router.get("/apple-library/status")
async def get_apple_library_status():
    """返回最新快照及其时效状态。"""
    snapshot = await asyncio.to_thread(dual_library_service.get_latest_snapshot)
    if not snapshot:
        return {"snapshot": None, "age_days": None, "is_stale": True}
    imported_at = datetime.fromisoformat(snapshot["imported_at"])
    age_days = max(0, (datetime.now(timezone.utc) - imported_at).days)
    return {"snapshot": snapshot, "age_days": age_days, "is_stale": age_days >= 30}


@router.get("/library/reconciliation")
async def get_library_reconciliation(
    status: Optional[Literal["both", "nas_only", "apple_only", "review"]] = None,
    search: Optional[str] = None,
    refresh_local: bool = Query(False, description="重新扫描本地音乐库"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """对比最新 Apple Music 快照和本地音乐库。"""
    snapshot = await asyncio.to_thread(dual_library_service.get_latest_snapshot)
    if not snapshot:
        raise HTTPException(status_code=409, detail="请先导入 Apple Music CSV 快照")
    if not await asyncio.to_thread(media_library_service.get_sources):
        raise HTTPException(status_code=409, detail="请先添加本地音乐库文件夹")
    local_tracks = await asyncio.to_thread(media_library_service.load_tracks, refresh_local)
    local_index_version = await asyncio.to_thread(media_library_service.get_index_version)
    global reconciliation_cache
    if (
        refresh_local
        or reconciliation_cache is None
        or reconciliation_cache["snapshot_id"] != snapshot["id"]
        or reconciliation_cache["local_index_version"] != local_index_version
    ):
        result = None if refresh_local else await asyncio.to_thread(
            dual_library_service.get_cached_reconciliation,
            snapshot["id"],
            local_index_version,
        )
        if result is None:
            result = await asyncio.to_thread(dual_library_service.reconcile, local_tracks)
            await asyncio.to_thread(
                dual_library_service.save_cached_reconciliation,
                snapshot["id"],
                local_index_version,
                result,
            )
        reconciliation_cache = {
            "snapshot_id": snapshot["id"],
            "local_index_version": local_index_version,
            "result": result,
        }
    else:
        result = reconciliation_cache["result"]
    entries = result["entries"]
    if status:
        entries = [entry for entry in entries if entry["status"] == status]
    if search:
        query = search.casefold()
        entries = [entry for entry in entries if _entry_contains(entry, query)]
    return {
        "snapshot": snapshot,
        "summary": result["summary"],
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "entries": entries[offset:offset + limit],
    }


def _entry_contains(entry: dict, query: str) -> bool:
    values = []
    for side in (entry.get("apple"), entry.get("local")):
        if side:
            values.extend(str(value) for value in side.values() if value)
    for candidate in entry.get("candidates", []):
        values.extend(str(value) for value in candidate.values() if value)
    return any(query in value.casefold() for value in values)


@router.post("/library/matches")
async def save_library_match(request: MatchDecisionRequest):
    """保存人工确认或否决的匹配结果。"""
    local_tracks = await asyncio.to_thread(media_library_service.load_tracks, False)
    if request.local_file_id not in {track["id"] for track in local_tracks}:
        raise HTTPException(status_code=404, detail="本地音乐文件不存在")
    try:
        await asyncio.to_thread(
            dual_library_service.save_match_decision,
            request.local_file_id,
            request.apple_track_key,
            request.decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    return {"status": "success"}


@router.post("/library/matches/batch")
async def save_library_matches_batch(request: BatchMatchDecisionRequest):
    """批量保存待确认曲目的人工匹配决定。"""
    local_tracks = await asyncio.to_thread(media_library_service.load_tracks, False)
    local_file_ids = {track["id"] for track in local_tracks}
    if any(match.local_file_id not in local_file_ids for match in request.matches):
        raise HTTPException(status_code=404, detail="存在已不在本地音乐库中的曲目")
    try:
        await asyncio.to_thread(
            dual_library_service.save_match_decisions,
            [(match.local_file_id, match.apple_track_key, match.decision) for match in request.matches],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_reconciliation_cache()
    return {"status": "success", "count": len(request.matches)}
