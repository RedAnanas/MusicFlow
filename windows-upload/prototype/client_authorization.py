"""从已登录 Windows 客户端一次性取得账号及资料库授权，不读取密码。"""

import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import uuid

from prototype.local_session import save_session


ROOT = Path(__file__).resolve().parents[1]
from runtime import PRIVATE, exclusive_lock
BUNDLE = PRIVATE / "apple-client-authorization.dpapi"
EXPECTED = "ef493424c5768e8f5ffaf182463bee367ec68fffe1d886c06302a83ae7d427f3"
PACKAGE = "AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"


class ClientAuthorizationError(Exception):
    """错误不包含账号标识、Cookie 或令牌。"""


def default_library_file():
    """使用 Windows 已重定向的音乐文件夹，不假设位于 C 盘。"""
    folder = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("4bd8d571-6d19-48d3-be97-422220080e43").bytes_le)
    result = ctypes.c_wchar_p()
    shell = ctypes.WinDLL("shell32")
    method = shell.SHGetKnownFolderPath
    method.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    method.restype = ctypes.c_long
    if method(ctypes.byref(folder), 0, None, ctypes.byref(result)) != 0:
        raise ClientAuthorizationError("无法定位 Windows 音乐文件夹，请选择资料库文件")
    try:
        return Path(result.value) / "Apple Music/Apple Music Library.musiclibrary/Library.musicdb"
    finally:
        ctypes.WinDLL("ole32").CoTaskMemFree(ctypes.cast(result, ctypes.c_void_p))


def library_persistent_id(path):
    """读取当前已验证 hfma 资料库头中的持久标识，不扫描歌曲记录。"""
    with Path(path).open("rb") as source:
        header = source.read(56)
    if len(header) != 56 or header[:4] != b"hfma" or not int.from_bytes(header[48:56], "little"):
        raise ClientAuthorizationError("资料库格式不属于已验证的 Apple Music Windows 版本")
    return f"{int.from_bytes(header[48:56], 'little'):016X}"


def process_path(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ClientAuthorizationError("无法读取客户端进程信息")
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise ClientAuthorizationError("无法核对客户端进程路径")
        return Path(buffer.value)
    finally:
        kernel.CloseHandle(handle)


def collect_session(device, pid):
    """读取结果仅保留在内存中，校验完成前不覆盖旧授权。"""
    target = process_path(pid)
    if target.name.casefold() != "amplibraryagent.exe" or hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED:
        raise ClientAuthorizationError("客户端版本变化，停止使用旧版函数偏移")
    result = {}

    def message(event, data):
        if event.get("type") == "send" and event.get("payload", {}).get("kind") == "private-session" and data:
            try:
                result["session"] = json.loads(data)
            except (ValueError, TypeError):
                pass

    connection = device.attach(pid)
    try:
        script = connection.create_script((ROOT / "scripts/bootstrap-session.js").read_text(encoding="utf-8"))
        script.on("message", message)
        script.load()
    finally:
        connection.detach()
    if "session" not in result:
        raise ClientAuthorizationError("客户端尚未就绪；请完成登录后重新读取")
    return result["session"]


def make_bundle(session, library_id):
    identity = session.get("library_identity", {})
    headers = session.get("headers", {})
    if not headers.get("X-Token") or not headers.get("X-Dsid"):
        raise ClientAuthorizationError("客户端尚未登录，请先在 Apple Music 中完成登录")
    if identity.get("dsid") != headers["X-Dsid"] or not identity.get("cuid") or not identity.get("troveid"):
        raise ClientAuthorizationError("资料库尚未就绪，请开启同步资料库并等待客户端载入")
    required = {"cloud-library-update-request", "cloud-library-update-check", "cloud-assets-update"}
    if not required.issubset(session.get("upload_configuration", {})):
        raise ClientAuthorizationError("客户端上传配置尚未载入，请稍后重试")
    common = {"cuid": identity["cuid"], "troveid": identity["troveid"], "itunes-platform": "Windows",
        "itunes-version": "1.6.4.90", "protocol-version": 1, "min-compatible-version": 1,
        "itunes-match-protocol-version": 16, "min-itunes-match-compatible-version": 4,
        "signature-generation-capable": True, "sims-are-optional": True,
        "auto-update": False, "cloud-manual-update": True, "machine-name": socket.gethostname()}
    return {"version": 1, "created_at": time.time(), "source": "official-client-one-click",
        "target_sha256": EXPECTED, "account": session,
        "context": {"version": 1, "common": common, "persistent-library-id": library_id, "itre": identity["itre"]}}


def authorize(library_file=None, progress=None):
    with exclusive_lock():
        return _authorize(library_file, progress)


def _authorize(library_file=None, progress=None):
    """无需手动 PID；必要时打开客户端，读取并原子保存同一份授权包。"""
    import frida

    progress = progress or (lambda message: None)
    device = frida.get_local_device()
    candidates = [p for p in device.enumerate_processes() if p.name.casefold() == "amplibraryagent.exe"]
    if not candidates:
        progress("正在打开 Apple Music，请在客户端中完成登录并开启同步资料库")
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + PACKAGE],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not candidates:
            time.sleep(1)
            candidates = [p for p in device.enumerate_processes() if p.name.casefold() == "amplibraryagent.exe"]
    if len(candidates) != 1:
        raise ClientAuthorizationError("没有找到唯一的 Apple Music 资料库进程，请打开客户端后重试")
    progress("正在核对客户端版本并读取授权")
    session = collect_session(device, candidates[0].pid)
    library_file = Path(library_file) if library_file else default_library_file()
    if not library_file.is_file():
        raise ClientAuthorizationError("未找到默认资料库，请选择正在使用的 Library.musicdb")
    bundle = make_bundle(session, library_persistent_id(library_file))
    temporary = BUNDLE.with_suffix(".pending.dpapi")
    save_session(temporary, bundle)
    temporary.replace(BUNDLE)
    return {"authorization_saved": True, "library_context_saved": True,
            "server_verified": False, "created_at": bundle["created_at"]}
