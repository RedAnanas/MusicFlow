import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# 创建日志目录
Path(settings.LOGS_DIR).mkdir(parents=True, exist_ok=True)

# 确保所有必需的目录存在
from app.config import ensure_directories
ensure_directories()

# 初始化日志服务
from app.services.logger_service import logger_service
logger = logging.getLogger(__name__)
logger_service.info("Starting MusicFlow API", "main")

app = FastAPI(
    title="MusicFlow",
    description="NAS 音乐转换与整理工具",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import router
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """根端点"""
    logger_service.info("Root endpoint accessed", "main")
    return {
        "message": "MusicFlow API is running",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    from app.services.conversion_engine import conversion_engine
    return {
        "status": "healthy",
        "version": "0.1.0",
        "conversion_engine": conversion_engine.get_stats()
    }


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    from app.services.conversion_engine import conversion_engine
    await conversion_engine.initialize()

    # 在后台启动任务队列处理
    import asyncio
    asyncio.create_task(conversion_engine.process_queue())

    logger_service.info("Application started", "main")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    from app.services.conversion_engine import conversion_engine
    await conversion_engine.shutdown()
    logger_service.info("Application shutting down", "main")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
