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
├─ VERSION                  唯一的项目版本来源
├─ logs/                    本地日志（Git 忽略）
├─ temp/                    临时文件和进程状态（Git 忽略）
├─ AGENTS.md                工程与协作规范
├─ CONTRIBUTING.md          开发流程入口
├─ docker-compose.yml       唯一的 Compose 入口
└─ pyproject.toml           Python 测试配置
```

## 本地开发

环境要求：Python 3.12+、Node.js 18+、FFmpeg/FFprobe。

```powershell
.\scripts\setup-windows.ps1
```

如需要环境变量，可将 `backend/.env.example` 复制为 `backend/.env`，Windows 路径可写为 `D:/Music/source`。业务输入、输出和 Apple Music 交接目录也可直接在界面中选择。然后通过 PowerShell 脚本管理服务：

```powershell
# 启动
.\scripts\musicflow.ps1 start

# 状态
.\scripts\musicflow.ps1 status

# 重启
.\scripts\musicflow.ps1 restart

# 停止
.\scripts\musicflow.ps1 stop

# 查看版本
.\scripts\musicflow.ps1 version

# 发布或升级前，只读检查现有数据能否被当前版本兼容
.\scripts\musicflow.ps1 preflight
```

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8082
- API 文档：http://127.0.0.1:8082/docs

## 质量检查

提交前必须执行：

```powershell
.\scripts\check.ps1
```

该脚本依次执行后端测试、Python 编译检查、前端生产构建、Compose 配置检查和 Git 空白错误检查。GitHub Actions 会在推送和拉取请求中执行同等质量门禁。

## Docker Compose

Docker 部署只启动一个 `musicflow` 服务。首次启动后，在网页“系统状态”页面点击安装 FFmpeg；应用会根据运行平台下载并校验对应版本。`data/` 保存配置、任务历史、日志和工具，`music/` 是容器可访问的音乐根目录。

```powershell
docker compose up -d --build
```

- Web UI：http://127.0.0.1:8080
- 容器 API 不直接暴露，网页会自动转发 `/api` 请求。

推送 `main` 会自动构建并发布 `redananas/musicflow` 的 `linux/amd64` 与 `linux/arm64` 镜像。版本唯一来自根目录 `VERSION`：Actions 会发布 `latest`、完整版本号（如 `0.2.0`）和短版本号（如 `0.2`）标签，并写入镜像元数据。首次发布前，在 GitHub 仓库 Secrets 中配置 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN`。

升级飞牛前，先用候选镜像挂载原有 `data` 目录运行只读预检。预检通过后再更新容器；预检不会创建、修改、备份或迁移数据。

```sh
docker run --rm -v /实际/data目录:/data:ro -e CONFIG_DIR=/data/config redananas/musicflow:0.2.0 python -m app.preflight
```

预检返回 `"status": "passed"` 才可升级；返回 `"blocked"` 时保留旧容器和数据，先处理报告中的错误。发布前也应备份 `data`，并在部署后检查 `/health` 的版本号。

## 文档

- [文档索引](docs/README.md)
- [系统架构](docs/ARCHITECTURE.md)
- [开发流程](docs/development/workflow.md)
- [服务管理](docs/development/service-management.md)
- [变更记录](docs/CHANGELOG.md)

## 数据边界

`config/*.json`、`logs/`、`temp/`、`data/` 和 `backend/.env` 都是本地运行数据，不进入版本库。仓库中的配置示例位于 `config/examples/`。
