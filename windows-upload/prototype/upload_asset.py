"""复刻已验证的资产描述符执行层；尚不负责歌曲会话、SAP 或预处理。"""

import argparse
from email.utils import formatdate
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class UploadError(Exception):
    """仅返回脱敏错误，避免把预签名地址和认证头写入日志。"""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_requests(descriptor: dict, asset: bytes, user_agent: str) -> list[Request]:
    """将服务器上传描述符与已预处理资产转换为独立 HTTP 请求。"""
    requests = []
    try:
        operations = descriptor["operations"]
        if not isinstance(operations, list) or not operations:
            raise UploadError("上传描述符没有操作")
        for operation in operations:
            endpoint = operation["endpoint"]
            if operation["method"] != "PUT":
                raise UploadError("尚未验证的资产上传方法")
            url = urlsplit(endpoint)
            host = url.hostname or ""
            if (url.scheme != "https" or not host.endswith(".blobstore.apple.com")
                    or url.username is not None or url.password is not None
                    or url.fragment or url.port not in (None, 443)):
                raise UploadError("上传地址不属于已验证的 Apple HTTPS 资产服务")
            content = operation["content"]
            if content["type"] == "byterange":
                offset, length = content["offset"], content["length"]
                # 独立歌词、封面接口使用十进制字符串，音频接口使用整数。
                if isinstance(offset, str) and offset.isascii() and offset.isdecimal():
                    offset = int(offset)
                if isinstance(length, str) and length.isascii() and length.isdecimal():
                    length = int(length)
                if (type(offset) is not int or type(length) is not int
                        or offset < 0 or length <= 0 or offset + length > len(asset)):
                    raise UploadError("上传数据范围超出预处理资产")
                body = asset[offset:offset + length]
            elif content["type"] == "verbatim":
                body = content["content"]
                if not isinstance(body, bytes):
                    raise UploadError("内嵌资产必须是二进制数据")
            else:
                raise UploadError("尚未验证的上传内容类型")
            headers = {}
            for item in operation.get("requiredHeaders", []) + operation.get("optionalHeaders", []):
                key = item["key"]
                value = item.get("value")
                if value is None and item.get("clientGenerated"):
                    if key.lower() == "date":
                        value = formatdate(usegmt=True)
                    elif key.lower() == "user-agent":
                        value = user_agent
                    else:
                        raise UploadError("尚未验证的客户端生成请求头")
                if not isinstance(key, str) or not isinstance(value, str):
                    raise UploadError("上传请求头格式无效")
                if "\r" in key + value or "\n" in key + value:
                    raise UploadError("上传请求头含换行")
                if key.lower() == "content-length" and value != str(len(body)):
                    raise UploadError("上传长度与描述符不一致")
                headers[key] = value
            requests.append(Request(endpoint, data=body, headers=headers, method="PUT"))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise UploadError("上传描述符格式无效") from None
    return requests


def upload_asset(descriptor: dict, asset: bytes, user_agent: str, progress=None) -> list[int]:
    """顺序执行资产上传；HTTP 成功不代表整首歌曲已入库。"""
    requests = build_requests(descriptor, asset, user_agent)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    statuses = []
    total = sum(len(request.data) for request in requests)
    sent = 0
    for request in requests:
        if progress:
            progress(sent, total)
        if progress:
            body = request.data

            def chunks():
                nonlocal sent
                for offset in range(0, len(body), 64 * 1024):
                    progress(min(sent, total - 1), total)
                    chunk = body[offset:offset + 64 * 1024]
                    yield chunk
                    sent += len(chunk)
                    # 最后一个字节留待服务端确认成功，避免提前显示完成。
                    progress(min(sent, total - 1), total)

            request.data = chunks()
            request.add_header("Content-Length", str(len(body)))
        try:
            with opener.open(request, timeout=150) as response:
                if not 200 <= response.status < 300:
                    raise UploadError(f"资产上传返回 HTTP {response.status}")
                statuses.append(response.status)
        except HTTPError as error:
            raise UploadError(f"资产上传返回 HTTP {error.code}") from None
        except (URLError, OSError):
            raise UploadError("资产上传连接失败") from None
    if progress:
        progress(total, total)
    return statuses


def main():
    parser = argparse.ArgumentParser(description="执行已获授权的 Apple 资产上传描述符；不创建歌曲会话")
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--asset", required=True, type=Path, help="工作票据要求的预处理资产文件")
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()
    try:
        descriptor = json.loads(args.descriptor.read_text(encoding="utf-8"))
        statuses = upload_asset(descriptor, args.asset.read_bytes(), args.user_agent)
    except UploadError as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, ValueError):
        parser.exit(1, "读取输入文件失败\n")
    print(json.dumps({"asset_http_statuses": statuses, "library_confirmed": False}))


if __name__ == "__main__":
    main()
