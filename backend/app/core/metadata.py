import logging
import base64
from pathlib import Path
from typing import Dict, Optional, List
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.mp4 import MP4, MP4Cover
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

            # 使用非 easy 模式读取，以便获取所有标签包括封面
            audio = MutagenFile(file_path)
            if audio is None:
                logger.warning(f"Cannot read metadata for {file_path}")
                return None

            # 对于 M4A/MP4 文件，需要使用不同的方式读取标签
            metadata = {}
            if hasattr(audio, 'tags') and audio.tags:
                # 读取文本标签（带错误处理）
                # M4A/MP4 格式使用 iTunes 风格的标签
                for tag_key, mutagen_key in [
                    ("title", "©nam"),
                    ("artist", "©ART"),
                    ("album", "©alb"),
                    ("albumartist", "aART"),
                    ("date", "©day"),
                    ("track", "trkn"),
                    ("disc", "disk"),
                    ("copyright", "cprt"),
                ]:
                    try:
                        if mutagen_key in audio.tags:
                            value = audio.tags[mutagen_key]
                            if isinstance(value, list) and len(value) > 0:
                                metadata[tag_key] = str(value[0])
                            elif isinstance(value, tuple):
                                # trkn 和 disk 返回元组 (track, total)
                                metadata[tag_key] = str(value[0])
                            else:
                                metadata[tag_key] = str(value)
                    except (ValueError, TypeError) as e:
                        # 某些格式的 tags 不支持 in 操作
                        pass

                # FLAC/MP3/OGG 格式使用不同的标签名称
                flac_tags = {
                    "title": "title",
                    "artist": "artist",
                    "album": "album",
                    "albumartist": "albumartist",
                    "date": "date",
                    "track": "tracknumber",
                    "disc": "discnumber",
                    "genre": "genre",
                    "comment": "comment",
                }
                for tag_key, mutagen_key in flac_tags.items():
                    try:
                        if mutagen_key in audio.tags:
                            value = audio.tags[mutagen_key]
                            if isinstance(value, list) and len(value) > 0:
                                metadata[tag_key] = str(value[0])
                            else:
                                metadata[tag_key] = str(value)
                    except (ValueError, TypeError) as e:
                        pass

            cover = self._extract_cover(audio)
            if cover:
                metadata["cover"] = cover

            return metadata

        except Exception as e:
            logger.error(f"Error reading metadata from {file_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
            field_mapping = {
                "track": "tracknumber",
                "disc": "discnumber",
                "year": "date",
            }
            for field in self.METADATA_FIELDS:
                if field in metadata and metadata[field] is not None:
                    try:
                        target_field = field_mapping.get(field, field)
                        audio[target_field] = metadata[field]
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"Could not write field '{field}' to {file_path}: {e}")
                        fail_count += 1
                        continue

            audio.save()

            # EasyMutagen 不能写入 MP4 的 covr 等原生封面标签，需重新以原生模式打开
            if "cover" in metadata and metadata["cover"]:
                cover = metadata["cover"]
                if "data" in cover and "mime" in cover:
                    try:
                        self._write_cover(file_path, cover)
                        success_count += 1
                        logger.info(f"Cover image added to {file_path}")
                    except Exception as e:
                        logger.warning(f"Could not write cover to {file_path}: {e}")
                        fail_count += 1

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
                pic = audio.pictures[0]
                return {
                    "data": pic.data,
                    "mime": pic.mime,
                    "type": pic.type,
                    "desc": pic.desc,
                }

            if isinstance(audio, MP4) and audio.tags and "covr" in audio.tags:
                pic = audio.tags["covr"][0]
                mime = "image/png" if pic.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
                return {"data": bytes(pic), "mime": mime, "type": 3, "desc": ""}

            if isinstance(audio, MP3) and audio.tags:
                pictures = audio.tags.getall("APIC")
                if pictures:
                    pic = pictures[0]
                    return {
                        "data": pic.data,
                        "mime": pic.mime,
                        "type": pic.type,
                        "desc": pic.desc,
                    }

            if isinstance(audio, (OggVorbis, OggOpus)) and audio.tags:
                values = audio.tags.get("metadata_block_picture", [])
                if values:
                    pic = Picture(base64.b64decode(values[0]))
                    return {
                        "data": pic.data,
                        "mime": pic.mime,
                        "type": pic.type,
                        "desc": pic.desc,
                    }
        except Exception as e:
            logger.warning(f"Error extracting cover: {e}")
        return None

    def _write_cover(self, file_path: str, cover: Dict) -> None:
        """使用各格式的原生标签接口写入封面"""
        audio = MutagenFile(file_path)
        if audio is None:
            raise ValueError(f"Cannot open file for cover writing: {file_path}")

        mime = cover["mime"]
        data = cover["data"]
        picture_type = cover.get("type", 3)
        description = cover.get("desc", "")

        if isinstance(audio, MP4):
            if audio.tags is None:
                audio.add_tags()
            image_format = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(data, imageformat=image_format)]
        elif isinstance(audio, FLAC):
            audio.clear_pictures()
            picture = Picture()
            picture.type = picture_type
            picture.mime = mime
            picture.desc = description
            picture.data = data
            audio.add_picture(picture)
        elif isinstance(audio, MP3):
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(APIC(mime=mime, type=picture_type, desc=description, data=data))
        elif isinstance(audio, (OggVorbis, OggOpus)):
            if audio.tags is None:
                audio.add_tags()
            picture = Picture()
            picture.type = picture_type
            picture.mime = mime
            picture.desc = description
            picture.data = data
            audio.tags["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
        else:
            raise ValueError(f"Unsupported cover format: {Path(file_path).suffix}")

        audio.save()


metadata_service = MetadataService()
