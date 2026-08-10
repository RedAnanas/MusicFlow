import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from app.models import Task, TaskStatus, Profile
from app.core import ffprobe_service, ffmpeg_service, metadata_service
from app.services.config_manager import config_manager
from app.config import settings

logger = logging.getLogger(__name__)


class ConversionEngine:
    """转换引擎 - 管理音频文件转换"""

    def __init__(self):
        self.active_tasks: Dict[str, Task] = {}
        self.task_history: Dict[str, Task] = {}
        self.task_queue: asyncio.Queue = None
        self.executor = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_TASKS)
        self.max_concurrent = settings.MAX_CONCURRENT_TASKS
        self.current_concurrent = 0
        self.running = False
        self.progress_callbacks: Dict[str, Callable] = {}

    async def initialize(self):
        """初始化转换引擎"""
        self.task_queue = asyncio.Queue()
        self.running = True
        logger.info(f"Conversion engine initialized (max concurrent: {self.max_concurrent})")

    async def shutdown(self):
        """关闭转换引擎"""
        self.running = False
        # 等待队列中的任务完成
        while not self.task_queue.empty():
            await asyncio.sleep(0.1)
        self.executor.shutdown(wait=True)
        logger.info("Conversion engine shut down")

    async def submit_task(
        self,
        task: Task,
        profile: Profile,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        提交转换任务到队列

        Args:
            task: 转换任务
            profile: 转换配置
            progress_callback: 进度回调函数

        Returns:
            bool: 是否成功提交
        """
        try:
            # 添加到队列
            await self.task_queue.put((task, profile, progress_callback))
            logger.info(f"Task {task.id} submitted to queue (queue size: {self.task_queue.qsize()})")
            return True
        except Exception as e:
            logger.error(f"Failed to submit task {task.id}: {e}")
            return False

    async def process_queue(self):
        """处理任务队列"""
        while self.running:
            try:
                # 检查是否可以接受新任务
                if self.current_concurrent >= self.max_concurrent:
                    await asyncio.sleep(0.1)
                    continue

                # 从队列获取任务
                try:
                    task, profile, progress_callback = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 执行转换
                self.current_concurrent += 1
                asyncio.create_task(
                    self._execute_conversion(task, profile, progress_callback)
                )

            except Exception as e:
                logger.error(f"Error processing queue: {e}")
                await asyncio.sleep(1)

    async def _execute_conversion(
        self,
        task: Task,
        profile: Profile,
        progress_callback: Optional[Callable]
    ):
        """执行单个转换任务"""
        try:
            # 在线程池中执行阻塞操作
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                self.executor,
                self._run_conversion_sync,
                task,
                profile,
                progress_callback
            )

            if success:
                logger.info(f"Task {task.id} completed successfully")
            else:
                logger.warning(f"Task {task.id} failed")

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = datetime.now()

        finally:
            self.current_concurrent -= 1
            # 从活动任务中移除
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            # 保存到历史记录
            self.task_history[task.id] = task

    def _run_conversion_sync(
        self,
        task: Task,
        profile: Profile,
        progress_callback: Optional[Callable]
    ) -> bool:
        """同步执行转换任务（在线程池中运行）"""
        try:
            # 更新任务状态
            task.status = TaskStatus.CONVERTING
            task.start_time = datetime.now()
            task.progress = 0.0
            self.active_tasks[task.id] = task

            # 调用进度回调
            if progress_callback:
                progress_callback(task)

            # 检查源文件
            source_path = Path(task.source_file)
            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {task.source_file}")

            # 检查源文件音频信息
            audio_info = ffprobe_service.get_audio_info(task.source_file)
            if audio_info is None:
                raise ValueError("Cannot read audio info from source file")

            # 确保输出目录存在
            output_path = Path(task.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 构建 FFmpeg 命令
            codec = profile.codec or self._get_default_codec(profile.output_format.value)
            bitrate = profile.bitrate
            sample_rate = profile.sample_rate if profile.sample_rate and profile.sample_rate > 0 else None
            channels = profile.channels

            # 执行转换
            logger.info(f"Starting conversion: {task.source_file} -> {task.output_file}")

            # 更新进度为 10%
            task.progress = 10.0
            if progress_callback:
                progress_callback(task)

            success = ffmpeg_service.convert(
                input_path=task.source_file,
                output_path=task.output_file,
                codec=codec,
                bitrate=bitrate,
                sample_rate=sample_rate,
                channels=channels,
                threads=settings.FFMPEG_THREADS
            )

            if not success:
                raise RuntimeError("FFmpeg conversion failed")

            # 更新进度为 80%
            task.progress = 80.0
            if progress_callback:
                progress_callback(task)

            # 验证输出文件
            output_info = ffprobe_service.get_audio_info(task.output_file)
            if output_info is None:
                raise RuntimeError("Output file validation failed")

            # 更新进度为 90%
            task.progress = 90.0
            if progress_callback:
                progress_callback(task)

            # 复制元数据
            if profile.metadata_policy.value == "keep":
                logger.info(f"Reading metadata from source: {task.source_file}")
                metadata = metadata_service.read_metadata(task.source_file)
                if metadata:
                    logger.info(f"Metadata read successfully: {list(metadata.keys())}")
                    # 检查关键元数据字段
                    for key in ['title', 'artist', 'album', 'track', 'date', 'cover']:
                        if key in metadata:
                            value = metadata[key]
                            if key == 'cover':
                                logger.info(f"  {key}: {'有封面图片' if value else '无'}")
                            else:
                                logger.info(f"  {key}: {value}")

                    logger.info(f"Writing metadata to output: {task.output_file}")
                    write_success = metadata_service.write_metadata(task.output_file, metadata)
                    logger.info(f"Metadata write result: {'成功' if write_success else '失败'}")
                else:
                    logger.warning(f"No metadata found in source file: {task.source_file}")
            else:
                logger.info(f"Metadata policy is '{profile.metadata_policy.value}', skipping metadata copy")

            # 任务完成
            task.status = TaskStatus.SUCCESS
            task.end_time = datetime.now()
            task.progress = 100.0

            # 调用进度回调
            if progress_callback:
                progress_callback(task)

            logger.info(f"Conversion completed: {task.output_file}")
            return True

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            task.status = TaskStatus.FAILED
            task.end_time = datetime.now()
            task.error = str(e)

            # 调用进度回调
            if progress_callback:
                progress_callback(task)

            return False

    def _get_default_codec(self, output_format: str) -> str:
        """获取默认编码器"""
        codec_map = {
            "m4a": "aac",
            "mp3": "libmp3lame",
            "flac": "flac",
            "alac": "alac",
            "wav": "pcm_s16le",
            "ogg": "libvorbis",
            "opus": "libopus",
        }
        return codec_map.get(output_format, "aac")

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]
        if task_id in self.task_history:
            return self.task_history[task_id]
        return None

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            task.status = TaskStatus.CANCELLED
            task.end_time = datetime.now()
            del self.active_tasks[task_id]
            self.task_history[task_id] = task
            return True
        return False

    def get_queue_size(self) -> int:
        """获取队列大小"""
        if self.task_queue:
            return self.task_queue.qsize()
        return 0

    def get_active_count(self) -> int:
        """获取活动任务数量"""
        return self.current_concurrent

    def get_stats(self) -> Dict[str, Any]:
        """获取转换引擎统计信息"""
        return {
            "queue_size": self.get_queue_size(),
            "active_count": self.get_active_count(),
            "max_concurrent": self.max_concurrent,
            "total_completed": len([t for t in self.task_history.values() if t.status == TaskStatus.SUCCESS]),
            "total_failed": len([t for t in self.task_history.values() if t.status == TaskStatus.FAILED]),
        }


# 全局转换引擎实例
conversion_engine = ConversionEngine()

