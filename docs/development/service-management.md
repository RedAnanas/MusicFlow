# MusicFlow WSL 项目管理

MusicFlow 前后端仅在 WSL 中运行。首次使用时，执行以下命令创建隔离的 Python 环境并安装前后端依赖：

```bash
# MusicFlow 后端依赖目前要求 Python 3.12
# 请确保 python3.12 与 python3.12-venv 已安装
./scripts/setup-wsl.sh
```

之后统一使用 `scripts/musicflow.sh`：

```bash
./scripts/musicflow.sh start
./scripts/musicflow.sh stop
./scripts/musicflow.sh restart
./scripts/musicflow.sh status
```

脚本会自动加载 NVM 中的 Node.js，并且只会停止经命令行校验确认为 MusicFlow 的服务。运行日志保存在项目的 `logs/` 目录，进程状态保存在已忽略的 `temp/run/` 目录。WSL 中的 Docker 检查需要先在 Docker Desktop 的 **Settings → Resources → WSL Integration** 启用 Ubuntu。

访问地址：

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8082
- API 文档：http://127.0.0.1:8082/docs
