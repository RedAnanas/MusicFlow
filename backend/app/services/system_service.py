import hashlib
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from app.config import settings


class SystemService:
    """管理运行环境检查与受控 FFmpeg 安装。"""

    RELEASE_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
    CHECKSUMS_URL = f"{RELEASE_BASE}/checksums.sha256"

    def managed_dir(self) -> Path:
        return Path(settings.DATA_DIR) / "tools" / "ffmpeg"

    def _asset_name(self) -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "windows" and machine in {"amd64", "x86_64"}:
            return "ffmpeg-master-latest-win64-gpl.zip"
        if system == "linux" and machine in {"amd64", "x86_64"}:
            return "ffmpeg-master-latest-linux64-gpl.tar.xz"
        if system == "linux" and machine in {"aarch64", "arm64"}:
            return "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
        raise ValueError(f"不支持自动安装 FFmpeg 的平台：{platform.system()} {platform.machine()}")

    def _managed_binary(self, name: str) -> Path:
        suffix = ".exe" if platform.system().lower() == "windows" else ""
        return self.managed_dir() / f"{name}{suffix}"

    def find_binary(self, name: str) -> tuple[str | None, str]:
        managed = self._managed_binary(name)
        if managed.is_file():
            return str(managed), "自动安装"
        configured = getattr(settings, f"{name.upper()}_PATH")
        if configured and configured != name and Path(configured).is_file():
            return configured, "自定义配置"
        system_path = shutil.which(configured or name)
        return (system_path, "系统环境") if system_path else (None, "未安装")

    def version(self, name: str) -> dict:
        path, source = self.find_binary(name)
        if not path:
            return {"installed": False, "source": source, "path": None, "version": None}
        try:
            output = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5, encoding="utf-8").stdout
            return {"installed": True, "source": source, "path": path, "version": output.splitlines()[0] if output else "已安装"}
        except (OSError, subprocess.SubprocessError):
            return {"installed": False, "source": "不可执行", "path": path, "version": None}

    def status(self) -> dict:
        data_dir = Path(settings.DATA_DIR)
        music_path = settings.MUSIC_SOURCE_DIR
        return {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "ffmpeg": self.version("ffmpeg"),
            "ffprobe": self.version("ffprobe"),
            "data_directory": {"path": str(data_dir), "writable": self._is_writable(data_dir)},
            "music_directory": {
                "path": music_path or None,
                "configured": bool(music_path),
                "available": bool(music_path and Path(music_path).is_dir()),
            },
        }

    @staticmethod
    def _is_writable(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False

    def install_ffmpeg(self) -> dict:
        asset = self._asset_name()
        target_dir = self.managed_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = target_dir / asset
        checksum_text = self._download_text(self.CHECKSUMS_URL)
        expected = next((line.split()[0] for line in checksum_text.splitlines() if line.rstrip().endswith(asset)), None)
        if not expected:
            raise RuntimeError("未找到官方下载文件的校验值")
        self._download_file(f"{self.RELEASE_BASE}/{asset}", archive)
        actual = self._sha256(archive)
        if actual.lower() != expected.lower():
            archive.unlink(missing_ok=True)
            raise RuntimeError("FFmpeg 下载文件校验失败")
        extract_dir = target_dir / "extracting"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir()
        self._extract(archive, extract_dir)
        for name in ("ffmpeg", "ffprobe"):
            source = next(extract_dir.rglob(f"{name}.exe" if platform.system().lower() == "windows" else name), None)
            if not source:
                raise RuntimeError(f"下载包中缺少 {name}")
            destination = self._managed_binary(name)
            shutil.copy2(source, destination)
            if platform.system().lower() != "windows":
                destination.chmod(destination.stat().st_mode | 0o111)
        archive.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return self.status()

    @staticmethod
    def _download_text(url: str) -> str:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")

    @staticmethod
    def _download_file(url: str, destination: Path) -> None:
        with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _extract(archive: Path, destination: Path) -> None:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as content:
                content.extractall(destination)
        else:
            with tarfile.open(archive) as content:
                content.extractall(destination, filter="data")


system_service = SystemService()
