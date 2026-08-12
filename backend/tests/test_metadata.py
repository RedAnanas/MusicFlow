import base64
import subprocess
from pathlib import Path

import pytest
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

from app.config import settings
from app.core.metadata import MetadataService


PNG_DATA = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def create_audio_file(path: Path, codec: str) -> None:
    """创建用于元数据测试的短音频文件"""
    ffmpeg_path = Path(settings.FFMPEG_PATH)
    if not ffmpeg_path.exists():
        pytest.skip("未找到 FFmpeg，跳过元数据集成测试")

    subprocess.run(
        [
            str(ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            "0.1",
            "-c:a",
            codec,
            "-y",
            str(path),
        ],
        check=True,
    )


def test_copy_flac_metadata_and_cover_to_m4a(tmp_path: Path) -> None:
    """FLAC 转 M4A 后应保留文本元数据和 PNG 封面"""
    source_path = tmp_path / "source.flac"
    output_path = tmp_path / "output.m4a"
    create_audio_file(source_path, "flac")
    create_audio_file(output_path, "aac")

    source = FLAC(source_path)
    source["title"] = "测试歌曲"
    source["artist"] = "测试歌手"
    source["album"] = "测试专辑"
    source["date"] = "2026"
    source["tracknumber"] = "3"
    picture = Picture()
    picture.type = 3
    picture.mime = "image/png"
    picture.data = PNG_DATA
    source.add_picture(picture)
    source.save()

    service = MetadataService()
    metadata = service.read_metadata(str(source_path))
    assert metadata is not None
    assert service.write_metadata(str(output_path), metadata)

    result = MP4(output_path)
    assert result.tags["©nam"] == ["测试歌曲"]
    assert result.tags["©ART"] == ["测试歌手"]
    assert result.tags["©alb"] == ["测试专辑"]
    assert result.tags["©day"] == ["2026"]
    assert result.tags["trkn"] == [(3, 0)]
    assert bytes(result.tags["covr"][0]) == PNG_DATA
    assert result.tags["covr"][0].imageformat == MP4Cover.FORMAT_PNG
