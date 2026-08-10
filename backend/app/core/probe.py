import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class FFprobeService:
    """FFprobe 服务 - 读取音频文件信息"""

    def __init__(self):
        from app.config import settings
        self.ffprobe_path = settings.FFPROBE_PATH

    def get_audio_info(self, file_path: str) -> Optional[Dict]:
        """
        获取音频文件详细信息

        Returns:
            Dict: 包含音频信息的字典，如果失败返回 None
        """
        try:
            # 验证文件存在
            if not Path(file_path).exists():
                logger.error(f"File not found: {file_path}")
                return None

            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )

            if result.returncode != 0:
                logger.error(f"FFprobe failed for {file_path}: {result.stderr}")
                return None

            import json
            data = json.loads(result.stdout)

            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                logger.warning(f"No audio stream found in {file_path}")
                return None

            format_info = data.get("format", {})

            return {
                "format": format_info.get("format_name"),
                "duration": float(format_info.get("duration", 0)),
                "bitrate": int(format_info.get("bit_rate", 0)),
                "size": int(format_info.get("size", 0)),
                "codec": audio_stream.get("codec_name"),
                "codec_long": audio_stream.get("codec_long_name"),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": audio_stream.get("channels"),
                "channel_layout": audio_stream.get("channel_layout"),
                "bits_per_sample": audio_stream.get("bits_per_sample"),
                "bits_per_raw_sample": audio_stream.get("bits_per_raw_sample"),
            }

        except subprocess.TimeoutExpired:
            logger.error(f"FFprobe timeout for {file_path}")
            return None
        except Exception as e:
            logger.error(f"FFprobe error for {file_path}: {e}")
            return None


ffprobe_service = FFprobeService()
