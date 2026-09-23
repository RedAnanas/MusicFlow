from fastapi import APIRouter
from app.api.routes import discovery, files, filesystem, library, tasks, profiles, watch_folders, settings as settings_api, logs, system

router = APIRouter()

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
