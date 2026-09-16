import json

from app.services.preflight_service import PreflightService


def test_preflight_accepts_legacy_watch_folder_without_writing(tmp_path):
    """旧监控目录配置可升级，且预检不能改写原文件。"""
    config_file = tmp_path / "watch_folders.json"
    original = {
        "folder-1": {
            "id": "folder-1",
            "name": "旧目录",
            "input_dir": "/music/source",
            "profile_ids": ["aac"],
            "output_dir": "/music/output",
        }
    }
    config_file.write_text(json.dumps(original), encoding="utf-8")

    report = PreflightService(tmp_path).check()

    assert report["status"] == "passed"
    assert report["warnings"] == ["检测到 1 个旧版监控目录，将在运行时兼容为转换输出规则"]
    assert json.loads(config_file.read_text(encoding="utf-8")) == original
    assert not (tmp_path / "profiles.json").exists()


def test_preflight_blocks_invalid_json_without_renaming_file(tmp_path):
    """损坏的持久化数据必须阻止升级，且保留原始证据文件。"""
    config_file = tmp_path / "tasks.json"
    config_file.write_text("{invalid", encoding="utf-8")

    report = PreflightService(tmp_path).check()

    assert report["status"] == "blocked"
    assert any("tasks.json 无法读取" in error for error in report["errors"])
    assert config_file.read_text(encoding="utf-8") == "{invalid"
    assert not (tmp_path / "tasks.json.bak").exists()


def test_preflight_blocks_schema_newer_than_candidate(tmp_path):
    """候选版本不能部署到比它更新的数据格式上。"""
    (tmp_path / "schema_versions.json").write_text(
        json.dumps({"watch_folders": 3}), encoding="utf-8"
    )

    report = PreflightService(tmp_path).check()

    assert report["status"] == "blocked"
    assert "watch_folders 数据版本 3 高于当前程序支持的版本 2" in report["errors"]
