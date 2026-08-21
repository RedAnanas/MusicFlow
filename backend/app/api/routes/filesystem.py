import os
import string
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings


router = APIRouter()


class FileSystemEntry(BaseModel):
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None


class DirectoryListing(BaseModel):
    path: str
    parent: Optional[str]
    entries: List[FileSystemEntry]
    truncated: bool = False


def _root_entries() -> List[FileSystemEntry]:
    roots: List[Path] = []
    if os.name == "nt":
        roots.extend(Path(f"{letter}:\\") for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists())
    else:
        roots.append(Path("/"))
        home = Path.home()
        if home != Path("/") and home.exists():
            roots.append(home)
        for container in (Path("/mnt"), Path("/Volumes")):
            if container.is_dir():
                try:
                    roots.extend(path for path in container.iterdir() if path.is_dir())
                except OSError:
                    continue

    unique = {}
    for root in roots:
        unique[str(root)] = FileSystemEntry(name=str(root), path=str(root), is_directory=True)
    return list(unique.values())


@router.get("/roots", response_model=List[FileSystemEntry])
async def get_roots():
    """返回当前 MusicFlow 进程可访问的文件系统入口。"""
    return _root_entries()


@router.get("/entries", response_model=DirectoryListing)
async def get_entries(
    path: str = Query(..., description="要浏览的绝对目录"),
    audio_only: bool = Query(True, description="仅显示支持的音频文件"),
    limit: int = Query(1000, ge=1, le=5000),
):
    """列出目录内容，文件始终由服务器读取，不经浏览器上传。"""
    directory = Path(path).expanduser()
    if not directory.is_absolute():
        raise HTTPException(status_code=400, detail="路径必须为绝对路径")
    if not directory.exists():
        raise HTTPException(status_code=404, detail="目录不存在")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="路径不是目录")

    entries: List[FileSystemEntry] = []
    try:
        children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for child in children:
            if child.name.startswith("."):
                continue
            is_directory = child.is_dir()
            if not is_directory and audio_only and child.suffix.lower()[1:] not in settings.SUPPORTED_FORMATS:
                continue
            try:
                size = None if is_directory else child.stat().st_size
            except OSError:
                size = None
            entries.append(FileSystemEntry(
                name=child.name,
                path=str(child),
                is_directory=is_directory,
                size=size,
            ))
            if len(entries) > limit:
                break
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="没有权限读取该目录") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法读取目录：{exc}") from exc

    parent = directory.parent if directory.parent != directory else None
    return DirectoryListing(
        path=str(directory),
        parent=str(parent) if parent else None,
        entries=entries[:limit],
        truncated=len(entries) > limit,
    )
