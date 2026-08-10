from fastapi import APIRouter
from app.api.routes import files, tasks, profiles, watch_folders, settings as settings_api, logs

router = APIRouter()

router.include_router(files.router, prefix="/files", tags=["Files"])
router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
router.include_router(profiles.router, prefix="/profiles", tags=["Profiles"])
router.include_router(watch_folders.router, prefix="/watch-folders", tags=["Watch Folders"])
router.include_router(settings_api.router, prefix="/settings", tags=["Settings"])
router.include_router(logs.router, prefix="/logs", tags=["Logs"])
