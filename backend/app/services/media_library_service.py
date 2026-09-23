import hashlib
import threading
from pathlib import Path
from typing import Optional

from app.config import settings
from app.core import ffprobe_service, metadata_service
from app.services.config_manager import config_manager
from app.services.dual_library_service import normalize_text
from app.services.file_index_service import FileIndexService, file_index_service


class MediaLibraryService:
    """管理仅供资料库对账使用的整理后媒体库。"""

    FILE_NAME = "media_library_sources.json"
    INDEX_SCOPE = "media_library"

    def __init__(self, index_service: Optional[FileIndexService] = None):
        self._tracks: list[dict] = []
        self._loaded = False
        self._index_service = index_service or file_index_service
        self._refresh_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    def get_sources(self) -> list[str]:
        return [source["path"] for source in self.get_named_sources()]

    def get_named_sources(self) -> list[dict[str, str]]:
        data = config_manager.load(self.FILE_NAME) or {}
        if "sources" in data:
            return [dict(source) for source in data["sources"]]
        return [{"name": Path(path).name or str(path), "path": str(path)} for path in data.get("paths", [])]

    def save_sources(self, sources: list[dict[str, str]]) -> list[dict[str, str]]:
        unique = []
        for source in sources:
            raw_path = source["path"]
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                raise ValueError("媒体库路径必须是服务器上的绝对路径")
            if not path.exists() or not path.is_dir():
                raise ValueError(f"媒体库目录不可访问：{raw_path}")
            normalized = str(path)
            name = source["name"].strip()
            if not name:
                raise ValueError("请填写媒体库目录名称")
            if normalized not in [item["path"] for item in unique]:
                unique.append({"name": name, "path": normalized})
        if not config_manager.save(self.FILE_NAME, {"sources": unique}):
            raise OSError("保存媒体库目录失败")
        self.invalidate()
        return unique

    def add_source(self, name: str, path: str) -> dict[str, str]:
        sources = self.get_named_sources()
        if path in [source["path"] for source in sources]:
            raise ValueError("媒体库目录已添加")
        return self.save_sources(sources + [{"name": name, "path": path}])[-1]

    def update_source(self, source_id: str, name: str, path: str) -> dict[str, str]:
        sources = self.get_named_sources()
        previous = next((source for source in sources if self.source_id(source["path"]) == source_id), None)
        if previous is None:
            raise ValueError("媒体库目录不存在")
        if any(source["path"] == path and source is not previous for source in sources):
            raise ValueError("媒体库目录已添加")
        updated = {"name": name, "path": path}
        self.save_sources([updated if source is previous else source for source in sources])
        if previous["path"] != path:
            self._index_service.remove_source(self.INDEX_SCOPE, previous["path"])
        return updated

    def remove_source(self, source_id: str) -> None:
        sources = self.get_named_sources()
        removed = next((source["path"] for source in sources if self.source_id(source["path"]) == source_id), None)
        remaining = [source for source in sources if self.source_id(source["path"]) != source_id]
        if len(remaining) == len(sources):
            raise ValueError("媒体库目录不存在")
        self.save_sources(remaining)
        self._index_service.remove_source(self.INDEX_SCOPE, removed or "")

    @staticmethod
    def source_id(path: str) -> str:
        return hashlib.md5(path.encode()).hexdigest()

    def invalidate(self) -> None:
        with self._lock:
            self._tracks = []
            self._loaded = False

    def load_tracks(self, refresh: bool = False) -> list[dict]:
        with self._lock:
            if refresh:
                self._tracks = self._scan_tracks()
                self._loaded = True
            elif not self._loaded:
                if self._index_service.has_snapshot(self.INDEX_SCOPE):
                    self._tracks = self._deduplicate(self._index_service.load(self.INDEX_SCOPE))
                    self._loaded = True
                    self._schedule_refresh()
                else:
                    self._tracks = self._scan_tracks()
                    self._loaded = True
            return list(self._tracks)

    def get_index_version(self) -> int:
        return self._index_service.get_version(self.INDEX_SCOPE)

    def index_output(self, path: Path) -> bool:
        """仅将落在整理媒体库中的新成品增量写入索引。"""
        source = next(
            (source for source in self.get_sources() if Path(source) in path.parents),
            None,
        )
        if source is None or not path.is_file():
            return False
        track = self._read_track(path)
        if track is None:
            return False
        with self._lock:
            self._index_service.upsert(self.INDEX_SCOPE, source, track)
            if self._loaded:
                self._tracks = self._deduplicate(
                    [item for item in self._tracks if item["path"] != str(path)] + [track]
                )
        return True

    def _scan_tracks(self) -> list[dict]:
        tracks = self._index_service.refresh(
            self.INDEX_SCOPE,
            self.get_sources(),
            self._read_track,
        )
        return self._deduplicate(tracks)

    @staticmethod
    def _deduplicate(indexed_tracks: list[dict]) -> list[dict]:
        tracks = []
        seen = set()
        for track in indexed_tracks:
            duplicate_key = (track["isrc"] or "").strip().upper() or (
                normalize_text(track["title"] or Path(track["filename"]).stem),
                normalize_text(track["artist"]),
                normalize_text(track["album"]),
            )
            if duplicate_key in seen:
                continue
            seen.add(duplicate_key)
            tracks.append(track)
        return tracks

    def _schedule_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return

        def refresh_index():
            try:
                refreshed = self._scan_tracks()
                with self._lock:
                    self._tracks = refreshed
            except Exception:
                return

        self._refresh_thread = threading.Thread(target=refresh_index, daemon=True)
        self._refresh_thread.start()

    @staticmethod
    def _iter_audio_files(directory: Path):
        try:
            candidates = directory.rglob("*")
            for path in candidates:
                if path.is_file() and path.suffix.lower()[1:] in settings.SUPPORTED_FORMATS:
                    yield path
        except OSError:
            return

    @staticmethod
    def _read_track(path: Path) -> dict | None:
        try:
            metadata = metadata_service.read_metadata(str(path)) or {}
            audio_info = ffprobe_service.get_audio_info(str(path)) or {}
            return {
                "id": hashlib.md5(str(path).encode()).hexdigest(),
                "path": str(path),
                "filename": path.name,
                "format": path.suffix.lower()[1:],
                "size": path.stat().st_size,
                "duration": audio_info.get("duration"),
                "sample_rate": audio_info.get("sample_rate"),
                "bit_depth": audio_info.get("bits_per_sample"),
                "bitrate": audio_info.get("bitrate"),
                "channels": audio_info.get("channels"),
                "artist": metadata.get("artist"),
                "album": metadata.get("album"),
                "title": metadata.get("title"),
                "track": metadata.get("track"),
                "year": metadata.get("date"),
                "genre": metadata.get("genre"),
                "isrc": (metadata.get("isrc") or "").strip().upper() or None,
            }
        except (OSError, ValueError):
            return None


media_library_service = MediaLibraryService()
