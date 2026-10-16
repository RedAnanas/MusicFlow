import asyncio
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.config_manager import config_manager
from app.services.musicdl_client import CONNECTION_CONFIG_FILE, MusicdlClient, MusicdlClientError, musicdl_client
from app.services.system_service import system_service

router = APIRouter()


class MusicdlConnectionUpdate(BaseModel):
    base_url: str


def save_musicdl_base_url(value: str) -> dict[str, str]:
    """保存不含凭据和附加路径的 musicdl 服务根地址。"""
    base_url = value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("musicdl 地址端口无效") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or base_url != f"{parsed.scheme}://{parsed.netloc}"
        or (port is not None and port < 1)
    ):
        raise ValueError("请输入不含账号、路径或参数的 HTTP 服务地址")
    if not config_manager.save(CONNECTION_CONFIG_FILE, {"base_url": base_url}):
        raise OSError("保存 musicdl 服务地址失败")
    musicdl_client.base_url = base_url
    return {"base_url": base_url}


def check_musicdl_connection() -> dict:
    client = MusicdlClient(base_url=musicdl_client.base_url, timeout=5)
    result = {
        "base_url": client.base_url,
        "connected": False,
        "version": None,
        "acquisition_supported": False,
        "error": None,
    }
    try:
        health = client.health()
        result["connected"] = health.get("status") == "healthy"
        result["version"] = health.get("version")
        if result["connected"]:
            result["acquisition_supported"] = client.supports_acquisition()
    except (MusicdlClientError, OSError, ValueError) as error:
        result["error"] = str(error)
    return result


@router.get("/musicdl")
async def get_musicdl_connection():
    """检查当前 musicdl 地址、版本和一键补齐接口。"""
    return await asyncio.to_thread(check_musicdl_connection)


@router.put("/musicdl")
async def update_musicdl_connection(request: MusicdlConnectionUpdate):
    """更新 musicdl 连接地址，保存后立即对发现音乐生效。"""
    try:
        return await asyncio.to_thread(save_musicdl_base_url, request.base_url)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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


@router.get('/apple-upload')
def upload_preparation():
    from app.services.apple_upload_setup import preparation_status
    return preparation_status()


@router.get('/apple-upload/desktop-tools')
def upload_desktop_tools():
    from fastapi.responses import Response
    from app.services.apple_upload_setup import desktop_tools
    return Response(desktop_tools(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="musicflow-authorization-tools.zip"'})


@router.post('/apple-upload/algorithms')
async def upload_algorithms(files: list[UploadFile]):
    from app.services.apple_upload_setup import install_algorithms, preparation_status
    try:
        if len(files) != 4:
            raise ValueError('需要四个算法文件')
        content = {}
        for file in files:
            if file.filename in content:
                raise ValueError('算法文件重复')
            data = await file.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError('单个算法文件不能超过 64 MiB')
            content[file.filename] = data
        await asyncio.to_thread(install_algorithms, content)
        return preparation_status()
    except (ValueError, OSError):
        raise HTTPException(400, '算法导入失败：请选择完整的四个匹配版本文件，并检查存储权限') from None


@router.post('/apple-upload/authorization')
async def upload_authorization(account: UploadFile, key: UploadFile | None = None):
    from app.services.apple_upload_setup import import_account, preparation_status
    try:
        data = await account.read(64 * 1024 * 1024 + 35)
        secret = await key.read(33) if key else None
        if len(data) > 64 * 1024 * 1024 + 34:
            raise ValueError('授权文件过大')
        await asyncio.to_thread(import_account, data, secret)
        return preparation_status()
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except OSError:
        raise HTTPException(400, '无法保存授权，请检查存储权限') from None
