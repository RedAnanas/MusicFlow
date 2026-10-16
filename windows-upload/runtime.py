"""当前运行环境的私密目录与授权/上传互斥锁。"""

from contextlib import contextmanager
import csv
import os
from pathlib import Path
import subprocess


PRIVATE = (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MusicFlow" / "upload" if os.name == "nt"
           else Path(os.environ.get("MUSICFLOW_UPLOAD_PRIVATE_DIR", "/data/config/apple-upload/state")))


def secure_directory(directory=None):
    directory = Path(directory) if directory is not None else PRIVATE
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        info = directory.stat()
        if directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError("服务端上传目录必须仅当前用户可访问")
        return
    result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True)
    sid = next(csv.reader(result.stdout.decode(errors="replace").strip().splitlines()))[1]
    subprocess.run(["icacls.exe", str(directory), "/inheritance:r", "/grant:r",
                    f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)


@contextmanager
def exclusive_lock():
    secure_directory()
    if os.name != "nt":
        import fcntl
        with (PRIVATE / "worker.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("已有服务端上传进程运行") from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return
    import msvcrt
    with (PRIVATE / "worker.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("已有上传或授权进程运行，请先正常退出") from None
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
