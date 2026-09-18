import os
import shutil
import uuid
from pathlib import Path

from app.config import settings


class AppleMusicHandoffService:
    """将已转换的音乐安全交接给 Apple Music 自动导入目录。"""

    MARKER_FILE = ".musicflow-apple-music-mounted"
    NETWORK_FILESYSTEMS = {"cifs", "smb3"}

    def __init__(self, require_network_mount: bool = False):
        self.require_network_mount = require_network_mount

    @staticmethod
    def _get_mount_filesystem(target_dir: Path) -> str | None:
        """返回 Linux 下覆盖目标目录的最具体文件系统类型。"""
        mountinfo = Path("/proc/self/mountinfo")
        if not mountinfo.is_file():
            return None

        target = os.path.abspath(target_dir)
        best_match = (0, None)
        try:
            lines = mountinfo.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None

        for line in lines:
            if " - " not in line:
                continue
            before, after = line.split(" - ", 1)
            fields = before.split()
            filesystem_fields = after.split()
            if len(fields) < 5 or not filesystem_fields:
                continue
            mount_point = fields[4].replace("\\040", " ")
            try:
                if os.path.commonpath([target, mount_point]) != mount_point:
                    continue
            except ValueError:
                continue
            if len(mount_point) > best_match[0]:
                best_match = (len(mount_point), filesystem_fields[0].lower())
        return best_match[1]

    def _check_import_directory(self, target_dir: Path, require_marker: bool = False):
        """确认目录本身可访问，避免把挂载断开误判为文件已被取走。"""
        try:
            if not target_dir.is_dir():
                raise FileNotFoundError(f"Apple Music 自动导入目录不可访问：{target_dir}")
            with os.scandir(target_dir):
                pass
            if self.require_network_mount:
                filesystem = self._get_mount_filesystem(target_dir)
                if filesystem not in self.NETWORK_FILESYSTEMS:
                    raise OSError(f"Apple Music SMB/CIFS 挂载不可用：{target_dir}")
            if require_marker and not (target_dir / self.MARKER_FILE).is_file():
                raise FileNotFoundError(f"Apple Music 挂载标记不可访问：{target_dir}")
        except OSError as exc:
            if isinstance(exc, FileNotFoundError) and (
                "自动导入目录不可访问" in str(exc) or "挂载标记不可访问" in str(exc)
            ):
                raise
            raise OSError(f"Apple Music 自动导入目录不可访问：{target_dir}（{exc}）") from exc

    def handoff(self, source_file: str, import_dir: str) -> str:
        source_path = Path(source_file)
        target_dir = Path(import_dir)
        if not source_path.is_file():
            raise FileNotFoundError(f"转换成品不存在：{source_file}")
        self._check_import_directory(target_dir)
        marker_path = target_dir / self.MARKER_FILE
        if not marker_path.exists():
            marker_path.write_text("MusicFlow Apple Music 挂载检测标记\n", encoding="utf-8")
        self._check_import_directory(target_dir, require_marker=True)

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
        import_path = Path(import_file)
        self._check_import_directory(import_path.parent, require_marker=True)
        return not import_path.exists()


apple_music_handoff_service = AppleMusicHandoffService(
    require_network_mount=settings.APPLE_MUSIC_REQUIRE_NETWORK_MOUNT,
)
