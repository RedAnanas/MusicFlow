# MusicFlow 项目管理脚本

Windows 开发环境统一使用 `scripts/musicflow.ps1` 管理前后端服务。

```powershell
# 启动
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\musicflow.ps1 start

# 停止
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\musicflow.ps1 stop

# 重启
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\musicflow.ps1 restart

# 查看状态
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\musicflow.ps1 status
```

脚本只停止由它记录的进程，或经命令行校验确认属于 MusicFlow 且监听 3000/8082 端口的进程，不会结束系统中其他 Python 或 Node.js 服务。

运行日志保存在项目的 `logs/` 目录，进程状态保存在已忽略的 `temp/run/` 目录。

访问地址：

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8082
- API 文档：http://127.0.0.1:8082/docs
