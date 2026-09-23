import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

from app.config import settings


class MusicdlClientError(RuntimeError):
    pass


class MusicdlClient:
    """musicdl 内部 HTTP API 客户端，令牌只在服务端使用。"""

    def __init__(self, base_url: Optional[str] = None, service_token: Optional[str] = None):
        self.base_url = (base_url or settings.MUSICDL_BASE_URL).rstrip("/")
        self.service_token = service_token if service_token is not None else settings.MUSICDL_SERVICE_TOKEN

    def _request(
        self,
        path: str,
        method: str = "GET",
        payload: Optional[dict] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ):
        data = None
        headers = {"Accept": "application/json"}
        if self.service_token:
            headers["X-MusicDL-Token"] = self.service_token
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            return urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            message = exc.reason
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error", message)
            except (UnicodeDecodeError, ValueError, AttributeError):
                pass
            raise MusicdlClientError(str(message)) from exc
        except urllib.error.URLError as exc:
            raise MusicdlClientError(f"无法连接 musicdl：{exc.reason}") from exc

    def _json(self, path: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
        with self._request(path, method, payload) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict:
        version = self._json("/api/version")
        return {"status": "healthy", **version}

    def sources(self) -> list[dict]:
        return self._json("/api/sources")

    def search_events(self, query: str, sources: Optional[list[str]] = None) -> Iterator[tuple[str, dict]]:
        params = {"q": query}
        if sources:
            params["sources"] = ",".join(sources)
        path = f"/api/search?{urllib.parse.urlencode(params)}"
        with self._request(path) as response:
            event = "message"
            data_lines = []
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        yield event, json.loads("\n".join(data_lines))
                    event = "message"
                    data_lines = []
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())

    def start_download(self, token: str) -> str:
        return self._json("/api/v1/downloads", "POST", {"token": token})["download_id"]

    def get_download(self, download_id: str) -> dict:
        return self._json(f"/api/v1/downloads/{download_id}")

    def download_file(self, download_id: str, target_path: Path, expected_sha256: str) -> tuple[int, str]:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f".{target_path.name}.musicflow-downloading")
        digest = hashlib.sha256()
        size = 0
        try:
            with self._request(f"/api/v1/downloads/{download_id}/file") as response, temp_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            actual_sha256 = digest.hexdigest()
            if expected_sha256 and actual_sha256 != expected_sha256:
                raise MusicdlClientError("musicdl 下载文件校验值不一致")
            temp_path.replace(target_path)
            return size, actual_sha256
        finally:
            temp_path.unlink(missing_ok=True)

    def cleanup_file(self, download_id: str) -> None:
        self._json(f"/api/v1/downloads/{download_id}/file", "DELETE")


musicdl_client = MusicdlClient()
