import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from app.models import Task, TaskStatus, Profile
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器 - 管理转换任务队列"""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.task_history_file = "tasks.json"

    def create_task(
        self,
        source_file: str,
        profile: Profile,
        output_dir: str
    ) -> Task:
        """
        创建转换任务

        Args:
            source_file: 源文件路径
            profile: 转换配置
            output_dir: 输出目录

        Returns:
            Task: 创建的任务
        """
        task_id = str(uuid.uuid4())

        # 构建输出文件路径
        output_path = self._build_output_path(source_file, profile, output_dir)

        task = Task(
            id=task_id,
            source_file=source_file,
            output_file=str(output_path),
            profile_id=profile.id,
            status=TaskStatus.WAITING,
            created_at=datetime.now()
        )

        self.tasks[task_id] = task
        self._save_tasks()

        logger.info(f"Created task {task_id}: {source_file} -> {output_path}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[float] = None,
        error: Optional[str] = None
    ):
        """更新任务状态"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = status

            if progress is not None:
                task.progress = progress

            if status == TaskStatus.CONVERTING:
                task.start_time = datetime.now()
            elif status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.end_time = datetime.now()

            if error:
                task.error = error

            self._save_tasks()

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status in [TaskStatus.WAITING, TaskStatus.CONVERTING]:
                self.update_task_status(task_id, TaskStatus.CANCELLED)
                return True
        return False

    def retry_task(self, task_id: str) -> Optional[Task]:
        """重试任务"""
        if task_id in self.tasks:
            old_task = self.tasks[task_id]
            if old_task.status == TaskStatus.FAILED:
                # 创建新任务
                new_task = Task(
                    id=str(uuid.uuid4()),
                    source_file=old_task.source_file,
                    output_file=old_task.output_file,
                    profile_id=old_task.profile_id,
                    status=TaskStatus.WAITING,
                    created_at=datetime.now()
                )
                self.tasks[new_task.id] = new_task
                self._save_tasks()
                return new_task
        return None

    def _build_output_path(
        self,
        source_file: str,
        profile: Profile,
        output_dir: str
    ) -> Path:
        """构建输出文件路径"""
        source_path = Path(source_file)

        # 使用配置的目录模板
        dir_template = profile.directory_template
        dir_path = self._apply_template(dir_template, source_path)

        # 使用配置的文件名模板
        filename_template = profile.filename_template
        filename = self._apply_template(filename_template, source_path, profile.output_format)

        return Path(output_dir) / dir_path / filename

    def _apply_template(
        self,
        template: str,
        source_path: Path,
        extension: Optional[str] = None
    ) -> str:
        """应用模板替换"""
        # 这里应该从元数据服务获取实际的元数据
        # 暂时使用文件名作为占位符
        stem = source_path.stem

        result = template.replace("{title}", stem)
        result = result.replace("{extension}", extension or source_path.suffix[1:])

        return result

    def _save_tasks(self):
        """保存任务到文件"""
        tasks_data = {task_id: task.dict() for task_id, task in self.tasks.items()}
        config_manager.save(self.task_history_file, tasks_data)

    def load_tasks(self):
        """从文件加载任务"""
        tasks_data = config_manager.load(self.task_history_file)
        if tasks_data:
            for task_id, task_dict in tasks_data.items():
                self.tasks[task_id] = Task(**task_dict)


task_manager = TaskManager()
