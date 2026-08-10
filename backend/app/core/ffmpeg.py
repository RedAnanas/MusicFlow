import subprocess
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegService:
    """FFmpeg 服务 - 音频转换"""

    def __init__(self):
        from app.config import settings
        self.ffmpeg_path = settings.FFMPEG_PATH

    def build_convert_command(
        self,
        input_path: str,
        output_path: str,
        codec: str,
        bitrate: Optional[int] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        threads: int = 2,
        extra_args: List[str] = None
    ) -> List[str]:
        """
        构建 FFmpeg 转换命令
        """
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-y",  # 覆盖输出文件
        ]

        # 音频编码器
        cmd.extend(["-c:a", codec])

        # 比特率
        if bitrate:
            cmd.extend(["-b:a", f"{bitrate}k"])

        # 采样率
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])

        # 声道
        if channels:
            cmd.extend(["-ac", str(channels)])

        # 线程数
        cmd.extend(["-threads", str(threads)])

        # 额外参数
        if extra_args:
            cmd.extend(extra_args)

        # 映射音频流
        cmd.extend(["-map", "0:a?"])

        # 输出文件
        cmd.append(output_path)

        return cmd

    def convert(
        self,
        input_path: str,
        output_path: str,
        codec: str,
        bitrate: Optional[int] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        threads: int = 2
    ) -> bool:
        """
        执行音频转换

        Returns:
            bool: 转换是否成功
        """
        try:
            # 验证输入文件存在
            if not Path(input_path).exists():
                logger.error(f"Input file not found: {input_path}")
                return False

            cmd = self.build_convert_command(
                input_path,
                output_path,
                codec,
                bitrate,
                sample_rate,
                channels,
                threads
            )

            logger.info(f"Running FFmpeg: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1小时超时
                encoding='utf-8'
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return False

            # 验证输出文件
            if not Path(output_path).exists():
                logger.error(f"Output file not created: {output_path}")
                return False

            file_size = Path(output_path).stat().st_size
            if file_size == 0:
                logger.error(f"Output file is empty: {output_path}")
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for {input_path}")
            return False
        except Exception as e:
            logger.error(f"FFmpeg error: {e}")
            return False


ffmpeg_service = FFmpegService()
