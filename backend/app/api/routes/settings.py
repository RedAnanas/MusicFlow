from fastapi import APIRouter, HTTPException

from app.services.configuration_backup import GeneralSettings as SettingsResponse, apply_general, current_general
from app.services.config_manager import config_manager

router = APIRouter()


@router.get('/', response_model=SettingsResponse)
async def get_settings():
    """获取当前通用设置。"""
    return current_general()


@router.put('/')
async def update_settings(settings_update: SettingsResponse):
    """持久保存设置，避免服务重启后丢失。"""
    if not config_manager.save('settings.json', settings_update.model_dump()):
        raise HTTPException(500, '保存通用设置失败')
    apply_general(settings_update)
    return {'status': 'success', 'message': '设置已保存，并发参数重启后生效'}
