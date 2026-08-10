import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.services.logger_service import logger_service

router = APIRouter()
logger = logging.getLogger(__name__)


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    module: str
    message: str
    details: Optional[str] = None


@router.get("/", response_model=List[LogEntry])
async def get_logs(
    level: Optional[str] = Query(None, description="日志级别：INFO, WARNING, ERROR, DEBUG"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    module: Optional[str] = Query(None, description="模块筛选")
):
    """获取日志"""
    try:
        logs = logger_service.get_logs(level=level, limit=limit, module=module)
        return logs
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        return []


@router.delete("/")
async def clear_logs():
    """清空日志"""
    try:
        logger_service.clear_logs()
        return {"status": "success", "message": "Logs cleared"}
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/stats")
async def get_log_stats():
    """获取日志统计"""
    try:
        logs = logger_service.get_logs(limit=10000)

        stats = {
            "total": len(logs),
            "info": 0,
            "warning": 0,
            "error": 0,
            "debug": 0,
        }

        for log in logs:
            level = log.level.lower()
            if level in stats:
                stats[level] += 1

        return stats
    except Exception as e:
        logger.error(f"Error getting log stats: {e}")
        return {"total": 0, "info": 0, "warning": 0, "error": 0, "debug": 0}
