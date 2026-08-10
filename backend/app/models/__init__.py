from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AudioFormat(str, Enum):
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"
    AAC = "aac"
    ALAC = "alac"
    WAV = "wav"
    APE = "ape"
    OGG = "ogg"
    OPUS = "opus"
    WMA = "wma"


class OutputFormat(str, Enum):
    M4A = "m4a"
    MP3 = "mp3"
    FLAC = "flac"
    ALAC = "alac"
    WAV = "wav"
    OGG = "ogg"
    OPUS = "opus"


class MetadataPolicy(str, Enum):
    KEEP = "keep"
    OVERWRITE = "overwrite"
    STRIP = "strip"


class CoverPolicy(str, Enum):
    KEEP = "keep"
    EMBED = "embed"
    KEEP_AND_EMBED = "keep_and_embed"
    STRIP = "strip"


class TaskStatus(str, Enum):
    WAITING = "waiting"
    CONVERTING = "converting"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class AudioInfo(BaseModel):
    format: Optional[str] = None
    duration: Optional[float] = None
    bitrate: Optional[int] = None
    size: Optional[int] = None
    codec: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None


class Metadata(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    albumartist: Optional[str] = None
    composer: Optional[str] = None
    genre: Optional[str] = None
    date: Optional[str] = None
    track: Optional[str] = None
    disc: Optional[str] = None
    comment: Optional[str] = None
    copyright: Optional[str] = None
    grouping: Optional[str] = None
    lyrics: Optional[str] = None
    cover: Optional[dict] = None


class Profile(BaseModel):
    id: str
    name: str
    enabled: bool = True
    output_format: OutputFormat
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None
    metadata_policy: MetadataPolicy = MetadataPolicy.KEEP
    cover_policy: CoverPolicy = CoverPolicy.EMBED
    filename_template: str = "{title}.{extension}"
    directory_template: str = "{album_artist}/{year} - {album}"
    output_dir: Optional[str] = None
    version: int = 1


class WatchFolder(BaseModel):
    id: str
    name: str
    input_dir: str
    profile_ids: List[str]
    auto_process: bool = True
    recursive_scan: bool = True
    scan_interval_minutes: int = 5
    output_dir: Optional[str] = None
    enabled: bool = True


class Task(BaseModel):
    id: str
    source_file: str
    output_file: str
    profile_id: str
    status: TaskStatus
    progress: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
