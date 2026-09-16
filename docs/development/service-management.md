# MusicFlow Windows 项目管理

MusicFlow 本地开发默认在 Windows PowerShell 中运行。首次使用时，请确保已安装 Python 3.12、Node.js 18+ 和 FFmpeg/FFprobe，然后执行：

```powershell
.\scripts\setup-windows.ps1
```

之后统一使用 `scripts\musicflow.ps1`：

```powershell
.\scripts\musicflow.ps1 start
.\scripts\musicflow.ps1 stop
.\scripts\musicflow.ps1 restart
.\scripts\musicflow.ps1 status
```

脚本会优先使用项目根目录下的 Windows `.venv`，并且只停止经命令行校验确认为 MusicFlow 的服务。运行日志保存在 `logs\`，进程状态保存在已忽略的 `temp\run\`。

本地业务路径使用 Windows 绝对路径，例如 `D:\Music\source`，也支持已由 Windows 访问的 UNC 网络路径。

访问地址：

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8082
- API 文档：http://127.0.0.1:8082/docs
