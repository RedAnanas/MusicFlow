"""用户配置备份、预览和恢复入口。"""
import json
import re

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.services import configuration_backup as backup
from app.services.config_manager import config_manager

router = APIRouter()


def download(value):
    return Response(json.dumps(value, ensure_ascii=False, indent=2), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="musicflow-configuration.json"', 'Cache-Control': 'no-store'})


@router.get('/export')
def export_configuration():
    return download(backup.export_bundle().model_dump(mode='json'))


@router.get('/backups/{backup_id}')
def download_previous_configuration(backup_id: str):
    if not re.fullmatch('[a-f0-9]{32}', backup_id):
        raise HTTPException(404, '配置备份不存在')
    value = config_manager.load(f'configuration-backups/{backup_id}.json')
    if value is None:
        raise HTTPException(404, '配置备份不存在')
    return download(value)


async def read_bundle(file):
    try:
        return backup.parse_bundle(await file.read(backup.MAX_BYTES + 1))
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.post('/preview')
async def preview_configuration(file: UploadFile):
    return backup.preview(await read_bundle(file))


@router.post('/import')
async def import_configuration(file: UploadFile, current_revision: str = Form(...)):
    bundle = await read_bundle(file)
    try:
        return await backup.import_bundle(bundle, current_revision)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except OSError as error:
        raise HTTPException(500, str(error)) from None
