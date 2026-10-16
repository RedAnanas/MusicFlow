from fastapi import APIRouter
from app.api.routes import discovery, files, filesystem, library, tasks, profiles, watch_folders, settings as settings_api, logs, system

router = APIRouter()

from app.api.routes import apple_music_uploads
router.include_router(apple_music_uploads.router, prefix="/apple-music", tags=["Apple Music 上传"])

router.include_router(files.router, prefix="/files", tags=["Files"])
router.include_router(filesystem.router, prefix="/filesystem", tags=["Filesystem"])
router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
router.include_router(profiles.router, prefix="/profiles", tags=["Profiles"])
router.include_router(watch_folders.router, prefix="/watch-folders", tags=["Watch Folders"])
router.include_router(settings_api.router, prefix="/settings", tags=["Settings"])
router.include_router(logs.router, prefix="/logs", tags=["Logs"])
router.include_router(system.router, prefix="/system", tags=["System"])
router.include_router(library.router, tags=["Library Reconciliation"])
router.include_router(discovery.router, tags=["Discovery and Acquisition"])

from app.api.routes import configuration
router.include_router(configuration.router, prefix="/system/configuration", tags=["配置备份"])
