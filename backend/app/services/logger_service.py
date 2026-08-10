import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from app.config import settings
from pydantic import BaseModel


class LogEntry(BaseModel):
    """日志条目模型"""
    timestamp: datetime
    level: str
    module: str
    message: str
    details: Optional[str] = None


class LoggerService:
    """日志服务 - 管理应用日志"""

    def __init__(self):
        self.log_dir = Path(settings.LOGS_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 配置日志
        self._setup_logging()

    def _setup_logging(self):
        """设置日志配置"""
        # 主日志
        self.app_logger = logging.getLogger('app')
        self.app_logger.setLevel(logging.INFO)

        # 文件处理器 - 应用日志（带轮转）
        app_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'app.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        app_handler.setLevel(logging.INFO)
        app_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

        # 文件处理器 - 转换日志
        conversion_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'conversion.log',
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        conversion_handler.setLevel(logging.INFO)
        conversion_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))

        # 文件处理器 - 错误日志
        error_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'error.log',
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
        ))

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

        # 添加处理器
        self.app_logger.addHandler(app_handler)
        self.app_logger.addHandler(error_handler)
        self.app_logger.addHandler(console_handler)

        # 转换日志
        self.conversion_logger = logging.getLogger('conversion')
        self.conversion_logger.addHandler(conversion_handler)
        self.conversion_logger.addHandler(console_handler)

    def info(self, message: str, module: str = "app"):
        """记录 INFO 级别日志"""
        self.app_logger.info(f"[{module}] {message}")

    def warning(self, message: str, module: str = "app"):
        """记录 WARNING 级别日志"""
        self.app_logger.warning(f"[{module}] {message}")

    def error(self, message: str, module: str = "app", exc_info: bool = False):
        """记录 ERROR 级别日志"""
        self.app_logger.error(f"[{module}] {message}", exc_info=exc_info)

    def debug(self, message: str, module: str = "app"):
        """记录 DEBUG 级别日志"""
        self.app_logger.debug(f"[{module}] {message}")

    def conversion_info(self, message: str):
        """记录转换日志"""
        self.conversion_logger.info(message)

    def conversion_error(self, message: str, exc_info: bool = False):
        """记录转换错误"""
        self.conversion_logger.error(message, exc_info=exc_info)

    def get_logs(
        self,
        level: Optional[str] = None,
        limit: int = 100,
        module: Optional[str] = None
    ) -> List[LogEntry]:
        """
        获取日志条目

        Args:
            level: 日志级别筛选
            limit: 返回数量限制
            module: 模块筛选

        Returns:
            List[LogEntry]: 日志条目列表
        """
        logs = []

        try:
            log_file = self.log_dir / 'app.log'
            if not log_file.exists():
                return logs

            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 从后向前读取（最新的在前）
            for line in reversed(lines):
                if len(logs) >= limit:
                    break

                try:
                    # 解析日志行
                    # 格式: 2026-08-09 23:42:35,812 - module - LEVEL - message
                    parts = line.strip().split(' - ', 3)
                    if len(parts) < 4:
                        continue

                    timestamp_str = parts[0]
                    log_module = parts[1]
                    level_str = parts[2]
                    message = parts[3]

                    # 解析时间戳
                    timestamp = datetime.strptime(
                        timestamp_str,
                        '%Y-%m-%d %H:%M:%S,%f'
                    )

                    # 应用筛选
                    if level and level_str != level.upper():
                        continue

                    if module and log_module != module:
                        continue

                    log_entry = LogEntry(
                        timestamp=timestamp,
                        level=level_str,
                        module=log_module,
                        message=message,
                    )

                    logs.append(log_entry)

                except (ValueError, IndexError):
                    # 解析失败，跳过这行
                    continue

        except Exception as e:
            self.error(f"Error reading logs: {e}", "logger")

        return logs

    def clear_logs(self):
        """清空日志文件"""
        try:
            log_files = [
                'app.log',
                'conversion.log',
                'error.log',
            ]

            for log_file in log_files:
                log_path = self.log_dir / log_file
                if log_path.exists():
                    log_path.unlink()

            self.info("Logs cleared", "logger")

        except Exception as e:
            self.error(f"Error clearing logs: {e}", "logger")


# 全局日志服务实例
logger_service = LoggerService()
