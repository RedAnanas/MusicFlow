import os
import shutil
import uuid
from pathlib import Path


class AppleMusicHandoffService:
    """将已转换的音乐安全交接给 Apple Music 自动导入目录。"""

    def handoff(self, source_file: str, import_dir: str) -> str:
        source_path = Path(source_file)
        target_dir = Path(import_dir)
        if not source_path.is_file():
            raise FileNotFoundError(f"转换成品不存在：{source_file}")

        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
        if target_path.exists():
            if target_path.stat().st_size == source_path.stat().st_size:
                return str(target_path)
            raise FileExistsError(f"自动导入目录存在同名文件：{target_path}")

        temp_path = target_dir / f".{source_path.name}.{uuid.uuid4().hex}.musicflow-copying"
        try:
            shutil.copy2(source_path, temp_path)
            if temp_path.stat().st_size != source_path.stat().st_size:
                raise IOError(f"交接文件大小校验失败：{target_path}")
            os.replace(temp_path, target_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

        return str(target_path)

    def is_received(self, import_file: str) -> bool:
        """文件从自动导入目录消失时，视为已被 Apple Music 取走。"""
        return not Path(import_file).exists()


apple_music_handoff_service = AppleMusicHandoffService()
