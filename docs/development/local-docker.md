# WSL 本地 Docker 验证环境

此环境用于验证 Linux/Docker 上传准备流程，独立于 Windows 开发版。桌面授权工具仍在 Windows 执行，生成的加密授权在容器页面导入。

- WSL 发行版：Ubuntu（WSL2），Docker Engine 与 Compose 安装于其中。
- 本地 Compose：`config/docker-local/compose.yml`（个人环境配置，不提交）。
- 容器：`musicflow-local`；页面：`http://127.0.0.1:18080/system#apple-upload`。
- 持久数据：WSL `/var/lib/musicflow-local/data`；音乐目录：Windows `D:\Music`（WSL `/mnt/d/Music`），容器内分别为 `/data`、`/music`。
- 不复用 Windows 开发环境的数据库、配置或任务记录。算法文件及真实授权不打入镜像。

以下为本机验证示例；`config/docker-local/compose.yml` 属于不提交的个人配置。其他环境以根目录 `docker-compose.yml` 为起点设置卷和端口。将命令中的 `<项目的WSL绝对路径>` 替换为实际项目路径，再从 PowerShell 执行：

```powershell
# 启动或更新此容器
wsl -d Ubuntu -u root -- docker compose -p musicflow-local -f <项目的WSL绝对路径>/config/docker-local/compose.yml up -d --build

# 检查状态
wsl -d Ubuntu -u root -- docker compose -p musicflow-local -f <项目的WSL绝对路径>/config/docker-local/compose.yml ps

# 停止此容器，保留持久数据
wsl -d Ubuntu -u root -- docker compose -p musicflow-local -f <项目的WSL绝对路径>/config/docker-local/compose.yml stop
```

Docker 服务随 WSL 的 systemd 启动；未新增 Windows 开机任务。若 WSL 被关闭，本机容器也随之停止。本地验证环境不等于 NAS 已部署。

镜像拉取代理保存在 WSL `/etc/systemd/system/docker.service.d/musicflow-proxy.conf`；代理不可用时拉取可能失败，但已运行容器不依赖此代理处理本机请求。上传准备接口的 Nginx 请求体限额为 260 MiB，可容纳四个各不超过 64 MiB 的算法文件；后端继续逐文件限额和 SHA-256 校验。

## 本轮验证记录

2026-10-16 已通过 Docker Engine 官方 `hello-world` 运行测试及 MusicFlow Linux/amd64 镜像构建。Nginx、后端健康接口、FFmpeg/FFprobe、Linux 上传准备状态和桌面工具下载均已实测。8 MiB 的错误算法测试包经 Nginx 到达后端，返回校验失败且没有安装文件。未导入真实授权、未创建歌曲上传任务；后续请在 18080 页面的系统设置完成个人材料导入。
