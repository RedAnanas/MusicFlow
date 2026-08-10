import logging
from pathlib import Path
from typing import Dict, Optional, List
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus

logger = logging.getLogger(__name__)


class MetadataService:
    """元数据服务 - 使用 Mutagen 处理音频元数据"""

    # 元数据字段映射
    METADATA_FIELDS = [
        "title",
        "artist",
        "album",
        "albumartist",
        "composer",
        "genre",
        "date",
        "year",
        "track",
        "disc",
        "comment",
        "copyright",
        "grouping",
        "lyrics",
    ]

    def __init__(self):
        self.supported_formats = {
            ".mp3": MP3,
            ".flac": FLAC,
            ".m4a": MP4,
            ".mp4": MP4,
            ".ogg": OggVorbis,
            ".opus": OggOpus,
        }

    def read_metadata(self, file_path: str) -> Optional[Dict]:
        """
        读取音频文件元数据

        Returns:
            Dict: 元数据字典
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            audio = MutagenFile(file_path, easy=True)
            if audio is None:
                logger.warning(f"Cannot read metadata for {file_path}")
                return None

            metadata = {
                "title": self._get_tag(audio, "title"),
                "artist": self._get_tag(audio, "artist"),
                "album": self._get_tag(audio, "album"),
                "albumartist": self._get_tag(audio, "albumartist"),
                "composer": self._get_tag(audio, "composer"),
                "genre": self._get_tag(audio, "genre"),
                "date": self._get_tag(audio, "date"),
                "track": self._get_tag(audio, "tracknumber"),
                "disc": self._get_tag(audio, "discnumber"),
                "comment": self._get_tag(audio, "comment"),
                "copyright": self._get_tag(audio, "copyright"),
                "grouping": self._get_tag(audio, "grouping"),
                "lyrics": self._get_tag(audio, "lyrics"),
            }

            # 提取封面
            cover = self._extract_cover(audio)
            if cover:
                metadata["cover"] = cover
            else:
                # 对于 M4A/MP4 文件，尝试从 covr 字段读取封面
                if "covr" in audio.tags:
                    try:
                        pic = audio.tags["covr"][0]
                        metadata["cover"] = {
                            "data": bytes(pic),
                            "mime": "image/jpeg",
                            "type": 3
                        }
                    except Exception as e:
                        logger.warning(f"Could not read cover from covr field: {e}")

            return metadata

        except Exception as e:
            logger.error(f"Error reading metadata from {file_path}: {e}")
            return None

    def write_metadata(self, file_path: str, metadata: Dict) -> bool:
        """
        写入元数据到音频文件

        Args:
            file_path: 文件路径
            metadata: 要写入的元数据字典

        Returns:
            bool: 是否成功
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return False

            audio = MutagenFile(file_path, easy=True)
            if audio is None:
                logger.error(f"Cannot open file for writing: {file_path}")
                return False

            # 写入文本元数据（带错误处理）
            success_count = 0
            fail_count = 0
            for field in self.METADATA_FIELDS:
                if field in metadata and metadata[field] is not None:
                    try:
                        audio[field] = metadata[field]
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"Could not write field '{field}' to {file_path}: {e}")
                        fail_count += 1
                        continue

            # 写入封面图片（带错误处理）
            if "cover" in metadata and metadata["cover"]:
                cover = metadata["cover"]
                if "data" in cover and "mime" in cover:
                    try:
                        # 根据文件类型选择不同的封面写入方式
                        file_ext = path.suffix.lower()
                        if file_ext in [".mp3", ".flac", ".ogg"]:
                            # MP3/FLAC/OGG 使用 add_picture
                            from mutagen.flac import Picture
                            pic = Picture()
                            pic.type = 3  # Front cover
                            pic.mime = cover["mime"]
                            pic.data = cover["data"]
                            audio.add_picture(pic)
                        elif file_ext in [".m4a", ".mp4"]:
                            # M4A/MP4 需要使用 MP4Cover
                            from mutagen.mp4 import MP4Cover
                            pic = MP4Cover(cover["data"], imageformat=MP4Cover.FORMAT_JPEG)
                            audio["covr"] = [pic]
                        else:
                            # 其他格式尝试使用通用方式
                            audio["APIC:Front"] = cover["data"]

                        success_count += 1
                        logger.info(f"Cover image added to {file_path}")
                    except Exception as e:
                        logger.warning(f"Could not write cover to {file_path}: {e}")
                        fail_count += 1

            audio.save()
            logger.info(f"Metadata written to {file_path}: {success_count} fields written, {fail_count} fields skipped")
            return True

        except Exception as e:
            logger.error(f"Error writing metadata to {file_path}: {e}")
            return False

    def _get_tag(self, audio, tag_name: str) -> Optional[str]:
        """安全获取标签值"""
        try:
            if tag_name in audio.tags:
                value = audio.tags[tag_name]
                if isinstance(value, list) and len(value) > 0:
                    return str(value[0])
                return str(value)
        except Exception:
            pass
        return None

    def _extract_cover(self, audio) -> Optional[Dict]:
        """提取封面图片"""
        try:
            if hasattr(audio, 'pictures') and audio.pictures:
                for pic in audio.pictures:
                    return {
                        "data": pic.data,
                        "mime": pic.mime,
                        "type": pic.type,
                        "desc": pic.desc,
                    }
        except Exception as e:
            logger.warning(f"Error extracting cover: {e}")
        return None


metadata_service = MetadataService()
