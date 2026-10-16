"""构造已确认格式的上传控制请求；不获取账号会话，也不发送网络请求。"""

import base64
import gzip
import plistlib
import re
from urllib.parse import urlsplit
from urllib.request import Request


class ControlRequestError(Exception):
    """错误不包含请求体、令牌、Cookie 或签名。"""


def build_control_request(endpoint, payload, auth_headers, signer, *, server_route=None):
    """先编码和选择压缩，再对最终发送的字节生成 SAP 签名。"""
    try:
        url = urlsplit(endpoint)
        download_hosts = ("genius-download-2.itunes.apple.com", "genius-download.itunes.apple.com")
        upload_hosts = ("genius-upload-2.itunes.apple.com", "genius-upload.itunes.apple.com")
        routes = {"downloadRequests": (download_hosts, "/SGCourier/downloadRequests"),
                  "uploadResponses": (download_hosts, "/SGCourier/uploadResponses"),
                  "updateLibrary": (upload_hosts, "/updateLibrary"),
                  "getLibraryUpdateResponse": (download_hosts, "/getLibraryUpdateResponse")}
        if server_route is not None:
            hosts, path = routes.get(server_route, ((), None))
            allowed_path = url.hostname in hosts and url.path in (path, f"{path}/") and bool(url.query)
        else:
            allowed_path = not url.query and url.path.startswith(tuple(
                f"/WebObjects/{name}.woa/wa/" for name in ("UCGovernor", "UCChannel", "SGCourier")))
            allowed_path = allowed_path or (url.hostname == "genius-3.itunes.apple.com"
                and url.path == "/SGCourier/updateAssets/" and not url.query)
        if (url.scheme != "https" or url.hostname not in (
                "genius-3.itunes.apple.com", "genius-upload-2.itunes.apple.com",
                "genius-download-2.itunes.apple.com", "genius-upload.itunes.apple.com",
                "genius-download.itunes.apple.com") or url.username or url.password
                or url.port not in (None, 443) or url.fragment or not allowed_path):
            raise ControlRequestError("控制请求地址不属于已验证的上传服务")
        if not isinstance(payload, dict):
            raise ControlRequestError("控制请求体必须是属性列表字典")
        headers = {}
        reserved = {"host", "content-type", "content-length", "content-encoding", "x-apple-actionsignature"}
        for key, value in auth_headers.items():
            if (not isinstance(key, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
                    or not isinstance(value, str) or "\r" in value or "\n" in value):
                raise ControlRequestError("账号请求头格式无效")
            if key.lower() in reserved:
                raise ControlRequestError("账号请求头不得覆盖传输字段或签名")
            headers[key] = value
        if set(payload) == {"preformatted-data"}:
            body = payload["preformatted-data"]
            if not isinstance(body, bytes) or not body.startswith(b"\x1f\x8b\x08"):
                raise ControlRequestError("预编码分支目前只支持已验证的 gzip 属性列表")
            headers["Content-Encoding"] = "gzip"
        else:
            xml = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)
            # 原生编码器截取 plist 标签段，并在前面保留 XML 声明，省略 DTD。
            body = b"".join(line for line in xml.splitlines(keepends=True) if not line.startswith(b"<!DOCTYPE plist"))
            compressed = gzip.compress(body, mtime=0)
            if len(compressed) < len(body):
                body = compressed
                headers["Content-Encoding"] = "gzip"
        headers["Content-Type"] = "application/x-apple-plist"
        headers["Content-Length"] = str(len(body))
        if signer is None:
            if server_route != "getLibraryUpdateResponse":
                raise ControlRequestError("只有已验证的补充字段请求可以省略 SAP 签名")
        else:
            signature = signer.sign(body)
            if not isinstance(signature, bytes) or not signature:
                raise ControlRequestError("SAP 没有返回有效签名")
            headers["X-Apple-ActionSignature"] = base64.b64encode(signature).decode("ascii")
        return Request(endpoint, data=body, headers=headers, method="POST")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ControlRequestError("控制请求参数格式无效") from None
