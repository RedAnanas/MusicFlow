from fastapi import APIRouter, HTTPException

from app.services.system_service import system_service

router = APIRouter()


@router.get("/")
async def get_system_status():
    """获取运行环境状态。"""
    return system_service.status()


@router.post("/ffmpeg/install")
async def install_ffmpeg():
    """下载并校验当前平台对应的 FFmpeg。"""
    try:
        return system_service.install_ffmpeg()
    except (OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
