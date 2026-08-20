# MusicFlow

MusicFlow 是面向 NAS/本地音乐库的自动监控、音频转换与元数据保留工具。后端采用 FastAPI，前端采用 Vue 3 与 Element Plus。

## 功能

- 监控目录并自动发现稳定的音频文件
- 支持 M4A、MP3、FLAC、OGG、Opus 等输出格式
- 支持 AAC、ALAC、FLAC、MP3 等编码器
- 保留文本元数据、歌词和封面
- 管理转换配置、监控目录和任务状态
- 支持 Docker Compose 部署

## 项目结构

```text
MusicFlow/
├─ backend/                 FastAPI 后端与测试
├─ frontend/                Vue 3 前端
├─ config/                  本地运行配置（Git 忽略）
│  └─ examples/             可提交的配置示例
├─ docs/                    架构、指南和历史文档
├─ scripts/                 启停、检查和环境安装脚本
├─ logs/                    本地日志（Git 忽略）
├─ temp/                    临时文件和进程状态（Git 忽略）
├─ AGENTS.md                工程与协作规范
├─ CONTRIBUTING.md          开发流程入口
├─ docker-compose.yml       唯一的 Compose 入口
└─ pyproject.toml           Python 测试配置
```

## 本地开发

环境要求：Python 3.12+、Node.js 18+、FFmpeg/FFprobe。

```bash
./scripts/setup-wsl.sh
```

按本机环境修改 `backend/.env`，目录使用 WSL 形式，例如 `/mnt/d/Music/source`。然后统一通过项目脚本管理服务：

```bash
# 启动
./scripts/musicflow.sh start

# 状态
./scripts/musicflow.sh status

# 重启
./scripts/musicflow.sh restart

# 停止
./scripts/musicflow.sh stop
```

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8082
- API 文档：http://127.0.0.1:8082/docs

## 质量检查

提交前必须执行：

```bash
./scripts/check.sh
```

该脚本依次执行后端测试、Python 编译检查、前端生产构建、Compose 配置检查和 Git 空白错误检查。GitHub Actions 会在推送和拉取请求中执行同等质量门禁。

## Docker Compose

默认使用项目内的 `data/` 作为音乐目录；也可通过环境变量映射真实路径：

```bash
export MUSIC_SOURCE_PATH=/mnt/d/Music/source
export MUSIC_OUTPUT_PATH=/mnt/d/Music/output
export MUSIC_ARCHIVE_PATH=/mnt/d/Music/archive
docker compose up -d --build
```

- Web UI：http://127.0.0.1:8080
- 后端 API：http://127.0.0.1:8082

## 文档

- [文档索引](docs/README.md)
- [系统架构](docs/ARCHITECTURE.md)
- [开发流程](docs/development/workflow.md)
- [服务管理](docs/development/service-management.md)
- [变更记录](docs/CHANGELOG.md)

## 数据边界

`config/*.json`、`logs/`、`temp/`、`data/` 和 `backend/.env` 都是本地运行数据，不进入版本库。仓库中的配置示例位于 `config/examples/`。
