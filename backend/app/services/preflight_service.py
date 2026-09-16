"""发布前持久化数据兼容性检查，只读且不修改配置文件。"""

import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError

from app.models import Profile, Task, WatchFolder
from app.version import APP_VERSION


CURRENT_SCHEMAS = {
    "profiles": 1,
    "tasks": 1,
    "watch_folders": 2,
    "library_sources": 1,
}


class PreflightService:
    """校验候选版本能否读取现有持久化数据。"""

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)

    def check(self) -> Dict[str, Any]:
        """返回兼容性报告；全程只读。"""
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []
        schema_versions = self._read_schema_versions(errors)

        self._check_profiles(checks, errors, schema_versions)
        self._check_tasks(checks, errors, schema_versions)
        self._check_watch_folders(checks, errors, warnings, schema_versions)
        self._check_library_sources(checks, errors, schema_versions)

        return {
            "status": "passed" if not errors else "blocked",
            "application_version": APP_VERSION,
            "config_dir": str(self.config_dir),
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
        }

    def _read_json(self, filename: str, errors: List[str]) -> Any | None:
        path = self.config_dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{filename} 无法读取：{error}")
            return None

    def _read_schema_versions(self, errors: List[str]) -> Dict[str, int]:
        data = self._read_json("schema_versions.json", errors)
        if data is None:
            return {}
        if not isinstance(data, dict):
            errors.append("schema_versions.json 必须是对象")
            return {}

        versions: Dict[str, int] = {}
        for name, version in data.items():
            if not isinstance(version, int) or version < 1:
                errors.append(f"schema_versions.json 中 {name} 的版本号无效")
                continue
            versions[name] = version
        return versions

    def _check_schema(self, name: str, checks: List[Dict[str, Any]], errors: List[str], versions: Dict[str, int]):
        version = versions.get(name, 1)
        supported = CURRENT_SCHEMAS[name]
        if version > supported:
            errors.append(f"{name} 数据版本 {version} 高于当前程序支持的版本 {supported}")
            return False
        checks.append({"name": name, "schema_version": version, "supported_version": supported, "status": "passed"})
        return True

    def _check_profiles(self, checks, errors, versions):
        if not self._check_schema("profiles", checks, errors, versions):
            return
        data = self._read_json("profiles.json", errors)
        if data is None:
            return
        if not isinstance(data, dict):
            errors.append("profiles.json 必须是对象")
            return
        self._validate_items("profiles.json", data, Profile, errors)

    def _check_tasks(self, checks, errors, versions):
        if not self._check_schema("tasks", checks, errors, versions):
            return
        data = self._read_json("tasks.json", errors)
        if data is None:
            return
        if not isinstance(data, dict):
            errors.append("tasks.json 必须是对象")
            return
        self._validate_items("tasks.json", data, Task, errors)

    def _check_watch_folders(self, checks, errors, warnings, versions):
        if not self._check_schema("watch_folders", checks, errors, versions):
            return
        data = self._read_json("watch_folders.json", errors)
        if data is None:
            return
        if not isinstance(data, dict):
            errors.append("watch_folders.json 必须是对象")
            return
        self._validate_items("watch_folders.json", data, WatchFolder, errors)
        legacy_count = sum(1 for folder in data.values() if isinstance(folder, dict) and not folder.get("targets") and folder.get("output_dir"))
        if legacy_count:
            warnings.append(f"检测到 {legacy_count} 个旧版监控目录，将在运行时兼容为转换输出规则")

    def _check_library_sources(self, checks, errors, versions):
        if not self._check_schema("library_sources", checks, errors, versions):
            return
        data = self._read_json("library_sources.json", errors)
        if data is None:
            return
        if not isinstance(data, dict) or not isinstance(data.get("paths", []), list) or not all(isinstance(path, str) for path in data.get("paths", [])):
            errors.append("library_sources.json 的 paths 必须是字符串数组")

    @staticmethod
    def _validate_items(filename: str, data: Dict[str, Any], model, errors: List[str]):
        for item_id, item in data.items():
            try:
                model.model_validate(item)
            except ValidationError as error:
                errors.append(f"{filename} 中 {item_id} 无法兼容：{error.errors()[0]['msg']}")
