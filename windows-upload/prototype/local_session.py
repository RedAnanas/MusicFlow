"""Windows 使用 DPAPI，服务端使用独立密钥保护授权与任务记录。"""

import ctypes
from ctypes import wintypes
import json
import os
from datetime import datetime
from email.utils import formatdate
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


class SessionError(Exception):
    """会话错误不包含认证材料。"""


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), buffer)
    output = _Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    method = api.CryptUnprotectData if decrypt else api.CryptProtectData
    method.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise SessionError("Windows 会话保护失败")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.WinDLL("kernel32").LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def save_session(path, session):
    """调用者须先限制私密目录访问权限；仅写密文。"""
    if os.name != "nt":
        from prototype.portable_session import PortableSessionError
        try:
            _server_store().save(path, session)
            return
        except (OSError, ValueError, PortableSessionError):
            raise SessionError("服务端会话保存失败") from None
    raw = json.dumps(session, ensure_ascii=False).encode("utf-8")
    encrypted = _crypt(raw)
    path = Path(path)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(path):
    """仅在匹配的私密环境加载；返回值不能输出到日志。"""
    if os.name != "nt":
        from prototype.portable_session import PortableSessionError
        try:
            return _server_store().load(path)
        except (OSError, ValueError, PortableSessionError):
            raise SessionError("读取服务端会话失败") from None
    try:
        return json.loads(_crypt(Path(path).read_bytes(), decrypt=True))
    except (OSError, ValueError):
        raise SessionError("读取本地授权会话失败") from None


def _server_store():
    """服务端必须显式提供密钥，不回退到明文或临时密钥。"""
    from prototype.portable_session import EncryptedSessionStore
    key = os.environ.get("MUSICFLOW_UPLOAD_KEY_FILE")
    if not key:
        raise SessionError("尚未配置服务端会话密钥")
    return EncryptedSessionStore(key)


def request_headers(session, endpoint, cuid=None):
    """按请求主机选择首次授权的 Cookie，避免把其他服务的 Cookie 混用。"""
    headers = dict(session["headers"])
    if "cookies_by_host" in session:
        cookie = session["cookies_by_host"].get(urlsplit(endpoint).hostname)
        headers.pop("Cookie", None)
        if cookie:
            headers["Cookie"] = cookie
    if cuid:
        headers["X-Apple-Cuid"] = cuid
    # 原生客户端使用 GMT 日期及当前系统时区相对 GMT 的秒数。
    headers["Date"] = formatdate(usegmt=True)
    headers["X-Apple-Tz"] = str(int(datetime.now().astimezone().utcoffset().total_seconds()))
    return headers
