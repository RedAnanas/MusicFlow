import asyncio
import json
import queue
import threading
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.acquisition_service import acquisition_service
from app.services.apple_catalog_service import apple_catalog_service
from app.services.dual_library_service import dual_library_service
from app.services.dual_library_config import dual_library_config
from app.services.media_library_service import media_library_service
from app.services.musicdl_client import MusicdlClientError, musicdl_client
from app.services.profile_manager import profile_manager
from app.services.watch_folder_manager import watch_folder_manager


router = APIRouter()
presence_index: Optional[dict] = None
presence_index_loading = False
presence_index_lock = threading.Lock()
presence_index_ready = threading.Event()


class AcquisitionRequest(BaseModel):
    selected_track: Optional[dict] = None
    local_file_id: Optional[str] = None
    desired_nas: bool = False
    desired_apple: bool = False


class DualLibraryConfigRequest(BaseModel):
    nas_watch_folder_id: str = ""
    apple_watch_folder_id: str = ""
    apple_storefront: str = "cn"


class DownloadDirectory(BaseModel):
    name: str
    path: str


class DownloadSettingsRequest(BaseModel):
    download_directories: list[DownloadDirectory]


class DownloadRequest(BaseModel):
    token: str
    directory_name: str


def _warm_presence_index() -> None:
    """在后台扫描整理媒体库，不能阻塞 musicdl 的搜索首条结果。"""
    global presence_index, presence_index_loading
    try:
        local_tracks = media_library_service.load_tracks(False)
        index = dual_library_service.build_presence_index(local_tracks)
        with presence_index_lock:
            presence_index = index
    finally:
        with presence_index_lock:
            presence_index_loading = False
        presence_index_ready.set()


def _get_presence_index() -> Optional[dict]:
    """返回已就绪索引；首次扫描改在后台完成。"""
    global presence_index_loading
    with presence_index_lock:
        if presence_index is not None:
            return presence_index
        if not presence_index_loading:
            presence_index_loading = True
            presence_index_ready.clear()
            threading.Thread(target=_warm_presence_index, daemon=True).start()
    return None


def invalidate_presence_index() -> None:
    """资料库数据变化后让下一次搜索重建存在状态索引。"""
    global presence_index
    with presence_index_lock:
        presence_index = None


@router.get("/discovery/status")
async def get_discovery_status():
    """返回 musicdl 连通性和双库目标配置，不暴露服务令牌。"""
    try:
        health = await asyncio.to_thread(musicdl_client.health)
        connected = health.get("status") == "healthy"
        error = None
    except MusicdlClientError as exc:
        connected = False
        health = None
        error = str(exc)
    target_config = dual_library_config.resolve()
    nas_folder = watch_folder_manager.get_watch_folder(target_config["nas_watch_folder_id"])
    apple_folder = watch_folder_manager.get_watch_folder(target_config["apple_watch_folder_id"])
    return {
        "musicdl_connected": connected,
        "musicdl": health,
        "musicdl_error": error,
        "nas_watch_folder_configured": bool(
            nas_folder and nas_folder.enabled and nas_folder.auto_process
        ),
        "apple_watch_folder_configured": bool(
            apple_folder and apple_folder.enabled and apple_folder.auto_process
        ),
    }


@router.get("/dual-library/config")
async def get_dual_library_config():
    config = dual_library_config.resolve()
    nas_folder = watch_folder_manager.get_watch_folder(config["nas_watch_folder_id"])
    apple_folder = watch_folder_manager.get_watch_folder(config["apple_watch_folder_id"])
    return {
        **config,
        "nas_watch_folder_name": nas_folder.name if nas_folder else "",
        "nas_watch_folder_input_dir": nas_folder.input_dir if nas_folder else "",
        "apple_watch_folder_name": apple_folder.name if apple_folder else "",
        "apple_watch_folder_input_dir": apple_folder.input_dir if apple_folder else "",
        "musicdl_base_url": settings.MUSICDL_BASE_URL,
        "musicdl_service_token_configured": bool(settings.MUSICDL_SERVICE_TOKEN),
    }


@router.put("/dual-library/config")
async def update_dual_library_config(request: DualLibraryConfigRequest):
    nas_watch_folder_id = request.nas_watch_folder_id.strip()
    apple_watch_folder_id = request.apple_watch_folder_id.strip()
    apple_storefront = request.apple_storefront.strip().lower()
    if len(apple_storefront) != 2 or not apple_storefront.isalpha():
        raise HTTPException(status_code=400, detail="Apple 曲库地区必须是两位国家或地区代码")
    if nas_watch_folder_id and apple_watch_folder_id == nas_watch_folder_id:
        raise HTTPException(status_code=400, detail="飞牛和 Apple Music 必须使用独立监控目录")

    def validate_folder(folder_id: str, target: str) -> None:
        if not folder_id:
            return
        folder = watch_folder_manager.get_watch_folder(folder_id)
        if not folder:
            raise HTTPException(status_code=400, detail="选择的监控目录不存在")
        if not folder.enabled or not folder.auto_process:
            raise HTTPException(status_code=400, detail="双库补齐只能使用已启用自动处理的监控目录")
        has_copy = any(item.type.value == "copy" for item in folder.targets)
        has_apple = any(
            item.type.value == "convert"
            and (profile := profile_manager.get_profile(item.profile_id or "")) is not None
            and profile.apple_music_handoff_enabled
            and bool(profile.apple_music_import_dir)
            for item in folder.targets
        )
        if target == "nas" and (not has_copy or has_apple):
            raise HTTPException(status_code=400, detail="飞牛补齐目录必须仅配置飞牛复制输出")
        if target == "apple" and (not has_apple or has_copy):
            raise HTTPException(status_code=400, detail="Apple Music 补齐目录必须仅配置 Apple Music 交接输出")

    validate_folder(nas_watch_folder_id, "nas")
    validate_folder(apple_watch_folder_id, "apple")
    try:
        return await asyncio.to_thread(
            dual_library_config.save,
            nas_watch_folder_id,
            apple_watch_folder_id,
            apple_storefront,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/discovery/sources")
async def get_discovery_sources():
    try:
        return await asyncio.to_thread(musicdl_client.sources)
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/discovery/apple-catalog/search")
async def search_apple_catalog(
    q: str = Query(..., min_length=1),
    country: str = Query("cn", min_length=2, max_length=2),
    limit: int = Query(10, ge=1, le=25),
):
    """查询 Apple Music 公开网页曲库候选，不代表已经加入个人资料库。"""
    try:
        return await asyncio.to_thread(apple_catalog_service.search, q, country, limit)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/discovery/download-settings")
async def get_download_settings():
    """读取 musicdl 的服务器下载目录配置。"""
    try:
        return await asyncio.to_thread(musicdl_client._json, "/api/settings")
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.put("/discovery/download-settings")
async def update_download_settings(request: DownloadSettingsRequest):
    """保存 musicdl 的服务器下载目录配置。"""
    try:
        return await asyncio.to_thread(
            musicdl_client._json,
            "/api/settings",
            "POST",
            request.model_dump(),
        )
    except MusicdlClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/discovery/search")
async def search_discovery(
    q: str = Query(..., min_length=1),
    sources: Optional[str] = None,
):
    """代理 musicdl SSE 搜索，并为每个结果补充双库存在状态。"""
    _get_presence_index()
    source_list = [source for source in (sources or "").split(",") if source] or None
    events: queue.Queue[Optional[str]] = queue.Queue()

    def worker():
        pending_tracks = []
        done_data = {}
        try:
            for event, data in musicdl_client.search_events(q.strip(), source_list):
                if event == "result":
                    current_presence_index = _get_presence_index()
                    if current_presence_index is None:
                        data.update({
                            "nas_present": False,
                            "apple_present": False,
                            "match_reason": "presence_pending",
                            "presence_pending": True,
                        })
                        pending_tracks.append(dict(data))
                    else:
                        data.update(dual_library_service.lookup_presence(data, current_presence_index))
                        data["presence_pending"] = False
                if event == "done":
                    done_data = data
                    continue
                events.put(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")

            if pending_tracks:
                presence_index_ready.wait(timeout=10)
                with presence_index_lock:
                    current_presence_index = presence_index
                if current_presence_index is not None:
                    for track in pending_tracks:
                        update = {
                            "token": track.get("token"),
                            "source": track.get("source"),
                            **dual_library_service.lookup_presence(track, current_presence_index),
                            "presence_pending": False,
                        }
                        events.put(
                            f"event: presence\ndata: {json.dumps(update, ensure_ascii=False)}\n\n"
                        )
            events.put(f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n")
        except Exception as exc:
            events.put(f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n")
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        yield "retry: 10000\n\n"
        while True:
            message = events.get()
            if message is None:
                return
            yield message

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _proxy_musicdl_audio(token: str, as_download: bool, range_header: Optional[str] = None) -> StreamingResponse:
    """通过 MusicFlow 代理 musicdl 音频，避免浏览器接触服务令牌。"""
    try:
        extra_headers = {"Range": range_header} if range_header else None
        response = musicdl_client._request(f"/api/stream/{quote(token, safe='')}", extra_headers=extra_headers)
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    def content():
        try:
            while chunk := response.read(1024 * 1024):
                yield chunk
        finally:
            response.close()

    headers = {"Accept-Ranges": response.headers.get("Accept-Ranges", "bytes")}
    for name in ("Content-Range", "Content-Length"):
        if value := response.headers.get(name):
            headers[name] = value
    content_type = response.headers.get_content_type() or "application/octet-stream"
    if as_download:
        extension = content_type.rsplit("/", 1)[-1].replace("x-", "") or "audio"
        headers["Content-Disposition"] = f'attachment; filename="musicflow-download.{extension}"'
    return StreamingResponse(content(), status_code=response.status, media_type=content_type, headers=headers)


@router.get("/discovery/stream/{token}")
async def stream_discovery_audio(token: str, request: Request):
    return await asyncio.to_thread(_proxy_musicdl_audio, token, False, request.headers.get("range"))


@router.get("/discovery/download/{token}")
async def download_discovery_audio(token: str):
    return await asyncio.to_thread(_proxy_musicdl_audio, token, True)


@router.post("/discovery/downloads", status_code=202)
async def create_discovery_download(request: DownloadRequest):
    """让 musicdl 在选定的服务器目录中创建下载任务。"""
    try:
        return await asyncio.to_thread(
            musicdl_client._json,
            "/api/download",
            "POST",
            request.model_dump(),
        )
    except MusicdlClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _proxy_download_progress(download_id: str) -> StreamingResponse:
    try:
        response = musicdl_client._request(f"/api/download/{quote(download_id, safe='')}/progress")
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    def content():
        try:
            while chunk := response.read(8192):
                yield chunk
        finally:
            response.close()

    return StreamingResponse(
        content(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/discovery/downloads/{download_id}/progress")
async def get_discovery_download_progress(download_id: str):
    return await asyncio.to_thread(_proxy_download_progress, download_id)


def _proxy_download_file(download_id: str) -> StreamingResponse:
    try:
        response = musicdl_client._request(f"/api/file/{quote(download_id, safe='')}")
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    def content():
        try:
            while chunk := response.read(1024 * 1024):
                yield chunk
        finally:
            response.close()

    headers = {}
    for name in ("Content-Disposition", "Content-Length"):
        if value := response.headers.get(name):
            headers[name] = value
    return StreamingResponse(
        content(),
        status_code=response.status,
        media_type=response.headers.get_content_type() or "application/octet-stream",
        headers=headers,
    )


@router.get("/discovery/downloads/{download_id}/file")
async def get_discovery_download_file(download_id: str):
    return await asyncio.to_thread(_proxy_download_file, download_id)


@router.get("/discovery/lyrics/{token}")
async def get_discovery_lyrics(token: str):
    try:
        return await asyncio.to_thread(musicdl_client._json, f"/api/lyric/{quote(token, safe='')}")
    except MusicdlClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/acquisitions", status_code=202)
async def create_acquisition(request: AcquisitionRequest):
    local_source_path = None
    if request.local_file_id:
        local_tracks = await asyncio.to_thread(media_library_service.load_tracks, False)
        local = next((track for track in local_tracks if track["id"] == request.local_file_id), None)
        if not local:
            raise HTTPException(status_code=404, detail="本地音乐文件不存在")
        local_source_path = local["path"]
        if request.selected_track is None:
            request.selected_track = {
                "song_name": local.get("title") or local.get("filename"),
                "singers": local.get("artist") or "",
                "album": local.get("album") or "",
                "isrc": local.get("isrc") or "",
            }
    try:
        job = await asyncio.to_thread(
            acquisition_service.create_job,
            request.selected_track,
            request.local_file_id,
            local_source_path,
            request.desired_nas,
            request.desired_apple,
        )
        if request.desired_apple:
            invalidate_presence_index()
        return job
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/acquisitions")
async def list_acquisitions(limit: int = Query(100, ge=1, le=1000)):
    return await asyncio.to_thread(acquisition_service.list_jobs, limit)


@router.get("/acquisitions/{job_id}")
async def get_acquisition(job_id: str):
    try:
        return await asyncio.to_thread(acquisition_service.get_job, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/acquisitions/{job_id}/retry", status_code=202)
async def retry_acquisition(job_id: str):
    try:
        return await asyncio.to_thread(acquisition_service.retry, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
